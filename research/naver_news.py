"""네이버 뉴스 검색 결과를 FestivalCase로 바꾼다.

네이버가 주는 description은 기사 전문이 아니라 검색 요약이다.
그래서 evidence_status는 항상 "snippet_only"이고, 요약만으로 세부 성과를 만들지 않는다.
"""

import html
from datetime import UTC, date, datetime

import httpx
from pydantic import ValidationError

from app.settings import Settings
from research.common import clean_text, make_case_id, parse_date
from schemas.contracts import FestivalCase

__all__ = ["NewsSearchError", "clean_text", "make_case_id", "parse_pub_date", "search_news"]

# 2026년 네이버 검색 API가 네이버 클라우드 플랫폼의 NAVER API HUB로 이관됐다.
# 키는 NCP 콘솔 > NAVER API HUB > Application > 인증 정보에서 받는다 (개발자센터 키는 쓸 수 없음).
# 문서: https://api.ncloud-docs.com/docs/naver-api-hub-search-news
API_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"

# 키가 틀리거나 권한이 없을 때 사용자에게 보여줄 안내
_STATUS_HINTS = {
    401: "인증에 실패했어요. .env의 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 확인해주세요.",
    403: "권한이 없어요. NAVER API HUB 애플리케이션에 뉴스 검색 API가 추가돼 있는지 확인해주세요.",
    429: "호출 한도를 넘었어요. 잠시 뒤에 다시 시도해주세요.",
}


class NewsSearchError(RuntimeError):
    """설정 누락이나 검색 실패. 메시지는 화면에 그대로 보여줘도 되는 문장이다."""


def parse_pub_date(value: str) -> date | None:
    """네이버 pubDate(RFC 822)를 날짜로 바꾼다. 읽지 못하면 추측하지 않고 None."""
    return parse_date(value)


def to_case(item: dict, retrieved_at: datetime) -> FestivalCase | None:
    """네이버 응답 항목 하나를 FestivalCase로 바꾼다. URL이 없거나 잘못되면 None."""
    url = html.unescape(item.get("originallink") or item.get("link") or "").strip()
    if not url:
        return None
    try:
        return FestivalCase(
            case_id=make_case_id(url),
            title=clean_text(item.get("title", "")),
            source_url=url,
            published_at=parse_pub_date(item.get("pubDate", "")),
            event_date=None,  # 게시일과 행사일은 다르다. 기사에서 확인하기 전까지 비워둔다
            retrieved_at=retrieved_at,
            evidence_text=clean_text(item.get("description", "")),
            evidence_status="snippet_only",
        )
    except ValidationError:
        return None


def _headers(settings: Settings) -> dict[str, str]:
    client_id = settings.naver_client_id.get_secret_value().strip()
    client_secret = settings.naver_client_secret.get_secret_value().strip()
    if not client_id or not client_secret:
        raise NewsSearchError(".env에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 입력해주세요.")
    return {"X-NCP-APIGW-API-KEY-ID": client_id, "X-NCP-APIGW-API-KEY": client_secret}


def search_news(
    query: str,
    display: int = 10,
    sort: str = "date",
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> list[FestivalCase]:
    """검색어 하나로 네이버 뉴스 첫 페이지를 가져와 FestivalCase 목록으로 돌려준다.

    sort: "date"(최신순) 또는 "sim"(정확도순). client는 테스트에서 가짜 응답을 넣을 때 쓴다.
    """
    query = query.strip()
    if not query:
        raise ValueError("검색어가 비어 있어요.")
    if not 1 <= display <= 100:
        raise ValueError("display는 1~100이어야 해요.")
    if sort not in {"date", "sim"}:
        raise ValueError('sort는 "date" 또는 "sim"이어야 해요.')

    settings = settings or Settings()
    headers = _headers(settings)
    params = {"query": query, "display": display, "start": 1, "sort": sort}
    own_client = client is None
    client = client or httpx.Client(timeout=settings.request_timeout_seconds)
    try:
        response = client.get(API_URL, headers=headers, params=params)
    except httpx.TimeoutException as exc:
        raise NewsSearchError("네이버 API 응답 시간이 초과됐어요.") from exc
    except httpx.HTTPError as exc:
        raise NewsSearchError("네이버 API에 연결하지 못했어요. 네트워크를 확인해주세요.") from exc
    finally:
        if own_client:
            client.close()

    if response.status_code != 200:
        # 헤더나 키는 메시지에 넣지 않는다
        hint = _STATUS_HINTS.get(response.status_code, "")
        raise NewsSearchError(f"네이버 API 오류 (HTTP {response.status_code}). {hint}".strip())

    try:
        items = response.json().get("items")
    except (ValueError, AttributeError) as exc:
        raise NewsSearchError("네이버 API 응답을 읽지 못했어요.") from exc
    if not isinstance(items, list):
        raise NewsSearchError("네이버 API 응답에 기사 목록이 없어요.")

    retrieved_at = datetime.now(UTC)
    cases = (to_case(item, retrieved_at) for item in items if isinstance(item, dict))
    return [case for case in cases if case is not None]
