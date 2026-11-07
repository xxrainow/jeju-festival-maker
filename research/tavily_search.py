"""Tavily 검색 결과를 FestivalCase로 바꾼다.

Tavily 약관(2026-01-13)은 검색 결과를 AI 도구에 넣는 것을 허용한다. 네이버 검색 API와 달리
사례 추출과 아이디어 생성의 LLM 입력으로 쓸 수 있다.
다만 기사 저작권은 그대로라서 원문은 저장하지 않고, 검색 요약(content)과 링크, 게시일만 쓴다.

문서: https://docs.tavily.com/documentation/api-reference/endpoint/search
"""

from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import ValidationError

from app.settings import Settings
from research.common import clean_text, make_case_id, parse_date
from schemas.contracts import FestivalCase

API_URL = "https://api.tavily.com/search"

Topic = Literal["general", "news"]
TimeRange = Literal["day", "week", "month", "year"]
Depth = Literal["basic", "advanced"]  # basic 1크레딧, advanced 2크레딧

# 사례 근거로 쓰기 어려운 곳: SNS·블로그(개인 게시물), 위키(편집 가능한 2차 자료).
# 2026-11-06 시험에서 이 출처들이 결과 대부분을 차지해 기본으로 뺀다.
DEFAULT_EXCLUDE_DOMAINS = [
    "facebook.com",
    "instagram.com",
    "threads.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "blog.naver.com",
    "m.blog.naver.com",
    "tistory.com",
    "namu.wiki",
]

_STATUS_HINTS = {
    401: "인증에 실패했어요. .env의 TAVILY_API_KEY를 확인해주세요.",
    429: "요청이 너무 많아요. 잠시 뒤에 다시 시도해주세요.",
    432: "요금제 한도를 넘었어요. Tavily 대시보드에서 남은 크레딧을 확인해주세요.",
    433: "종량제 한도를 넘었어요. Tavily 대시보드에서 한도를 확인해주세요.",
}


class TavilySearchError(RuntimeError):
    """설정 누락이나 검색 실패. 메시지는 화면에 그대로 보여줘도 되는 문장이다."""


def to_case(result: dict, retrieved_at: datetime) -> FestivalCase | None:
    """Tavily 결과 하나를 FestivalCase로 바꾼다. URL이 없거나 잘못되면 None."""
    url = (result.get("url") or "").strip()
    if not url:
        return None
    try:
        return FestivalCase(
            case_id=make_case_id(url),
            title=clean_text(result.get("title", "")),
            source_url=url,
            published_at=parse_date(result.get("published_date")),
            event_date=None,  # 게시일과 행사일은 다르다. 기사에서 확인하기 전까지 비워둔다
            retrieved_at=retrieved_at,
            evidence_text=clean_text(result.get("content", "")),
            evidence_status="snippet_only",  # content는 Tavily가 뽑은 일부 문단이다
        )
    except ValidationError:
        return None


def search_cases(
    query: str,
    max_results: int = 10,
    *,
    topic: Topic = "general",
    time_range: TimeRange | None = "year",
    search_depth: Depth = "advanced",
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> list[FestivalCase]:
    """검색어 하나로 Tavily를 검색해 FestivalCase 목록으로 돌려준다.

    topic="general"이면 국가를 대한민국으로 좁힌다 (Tavily는 general에서만 country를 받는다).
    search_depth="advanced"(2크레딧)가 기본이다. basic은 결과가 적고 요약이 짧았다 (2026-11-06 시험).
    exclude_domains를 주지 않으면 DEFAULT_EXCLUDE_DOMAINS를 뺀다. 빈 목록을 주면 아무것도 빼지 않는다.
    client는 테스트에서 가짜 응답을 넣을 때 쓴다.
    """
    query = query.strip()
    if not query:
        raise ValueError("검색어가 비어 있어요.")
    if not 1 <= max_results <= 20:
        raise ValueError("max_results는 1~20이어야 해요.")

    settings = settings or Settings()
    api_key = settings.tavily_api_key.get_secret_value().strip()
    if not api_key:
        raise TavilySearchError(".env에 TAVILY_API_KEY를 입력해주세요.")

    body: dict = {
        "query": query,
        "max_results": max_results,
        "topic": topic,
        "search_depth": search_depth,
        "include_answer": False,  # Tavily가 만든 요약 답변은 쓰지 않는다 (출처 없는 문장)
        "include_raw_content": False,  # 원문은 받지도 저장하지도 않는다
        "include_published_date": True,
    }
    if time_range:
        body["time_range"] = time_range
    if topic == "general":
        body["country"] = "south korea"
    if include_domains:
        body["include_domains"] = include_domains
    excluded = DEFAULT_EXCLUDE_DOMAINS if exclude_domains is None else exclude_domains
    if excluded:
        body["exclude_domains"] = excluded

    own_client = client is None
    client = client or httpx.Client(timeout=settings.request_timeout_seconds)
    try:
        response = client.post(
            API_URL, json=body, headers={"Authorization": f"Bearer {api_key}"}
        )
    except httpx.TimeoutException as exc:
        raise TavilySearchError("Tavily 응답 시간이 초과됐어요.") from exc
    except httpx.HTTPError as exc:
        raise TavilySearchError("Tavily에 연결하지 못했어요. 네트워크를 확인해주세요.") from exc
    finally:
        if own_client:
            client.close()

    if response.status_code != 200:
        # 헤더나 키는 메시지에 넣지 않는다
        hint = _STATUS_HINTS.get(response.status_code, "")
        raise TavilySearchError(f"Tavily 오류 (HTTP {response.status_code}). {hint}".strip())

    try:
        results = response.json().get("results")
    except (ValueError, AttributeError) as exc:
        raise TavilySearchError("Tavily 응답을 읽지 못했어요.") from exc
    if not isinstance(results, list):
        raise TavilySearchError("Tavily 응답에 검색 결과 목록이 없어요.")

    retrieved_at = datetime.now(UTC)
    cases: dict[str, FestivalCase] = {}
    for result in results:
        if isinstance(result, dict) and (case := to_case(result, retrieved_at)):
            cases.setdefault(case.case_id, case)
    return list(cases.values())
