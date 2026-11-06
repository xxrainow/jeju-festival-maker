import json
from datetime import UTC, date, datetime

import httpx
import pytest

from app.settings import Settings
from research.common import make_case_id, parse_date
from research.tavily_search import TavilySearchError, search_cases, to_case

# Tavily 응답 형식을 흉내 낸 가짜 결과. 실제 기사가 아니다.
RESULT_A = {
    "title": "○○군 커피 축제, 농가 참여 시음 체험",
    "url": "https://example.com/news/1",
    "content": "지역 농가가 참여한 시음 부스와 원두 마켓을   운영했다.",
    "score": 0.81,
    "published_date": "Tue, 21 Oct 2026 09:30:00 GMT",
}
RESULT_B = {
    "title": "△△시 딸기 축제",
    "url": "https://example.com/news/2",
    "content": "체험 프로그램 운영",
    "score": 0.52,
    "published_date": None,
}

KEY = Settings(tavily_api_key="tvly-test-key")
NO_KEY = Settings(tavily_api_key="", _env_file=None)
NOW = datetime(2026, 11, 6, 5, 30, tzinfo=UTC)


def fake_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def respond(results, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"results": results})

    return handler


def test_parse_date_reads_both_formats():
    assert parse_date("Tue, 21 Oct 2026 09:30:00 GMT") == date(2026, 10, 21)
    assert parse_date("2026-10-21T09:30:00Z") == date(2026, 10, 21)
    assert parse_date("2026-10-21") == date(2026, 10, 21)
    assert parse_date("모름") is None
    assert parse_date(None) is None


def test_to_case_matches_contract():
    case = to_case(RESULT_A, NOW)
    assert case.case_id == make_case_id("https://example.com/news/1")
    assert case.published_at == date(2026, 10, 21)
    assert case.event_date is None
    assert case.retrieved_at == NOW
    assert case.evidence_text == "지역 농가가 참여한 시음 부스와 원두 마켓을 운영했다."
    assert case.evidence_status == "snippet_only"
    assert to_case(RESULT_B, NOW).published_at is None
    assert to_case({**RESULT_A, "url": ""}, NOW) is None
    assert to_case({**RESULT_A, "url": "주소 아님"}, NOW) is None


def test_search_sends_expected_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": [RESULT_A, RESULT_B, RESULT_A]})

    cases = search_cases("커피 축제", max_results=5, settings=KEY, client=fake_client(handler))
    assert len(cases) == 2  # 같은 URL은 하나로
    assert seen["url"] == "https://api.tavily.com/search"
    assert seen["auth"] == "Bearer tvly-test-key"
    body = seen["body"]
    assert body["query"] == "커피 축제"
    assert body["max_results"] == 5
    assert body["country"] == "south korea"
    assert body["time_range"] == "year"
    assert body["include_raw_content"] is False  # 원문은 받지 않는다
    assert body["include_answer"] is False
    assert body["search_depth"] == "advanced"
    assert "instagram.com" in body["exclude_domains"]  # SNS는 기본으로 뺀다


def test_news_topic_has_no_country_and_domains_pass_through():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": []})

    search_cases(
        "축제",
        topic="news",
        time_range=None,
        include_domains=["korea.kr"],
        exclude_domains=[],
        settings=KEY,
        client=fake_client(handler),
    )
    assert "exclude_domains" not in seen["body"]  # 빈 목록이면 아무것도 빼지 않는다
    assert "country" not in seen["body"]
    assert "time_range" not in seen["body"]
    assert seen["body"]["include_domains"] == ["korea.kr"]


def test_missing_key_raises_clear_error():
    with pytest.raises(TavilySearchError, match="TAVILY_API_KEY"):
        search_cases("축제", settings=NO_KEY, client=fake_client(respond([])))


@pytest.mark.parametrize("status", [401, 429, 432, 433, 500])
def test_http_error_message_hides_key(status):
    with pytest.raises(TavilySearchError) as exc:
        search_cases("축제", settings=KEY, client=fake_client(respond([], status)))
    assert f"HTTP {status}" in str(exc.value)
    assert "tvly-test-key" not in str(exc.value)


def test_network_and_format_errors_are_wrapped():
    def broken(request):
        raise httpx.ConnectError("연결 실패")

    with pytest.raises(TavilySearchError, match="연결"):
        search_cases("축제", settings=KEY, client=fake_client(broken))

    def wrong_shape(request):
        return httpx.Response(200, json={"wrong": []})

    with pytest.raises(TavilySearchError, match="결과 목록"):
        search_cases("축제", settings=KEY, client=fake_client(wrong_shape))


@pytest.mark.parametrize("kwargs", [{"query": " "}, {"query": "축제", "max_results": 0}])
def test_invalid_arguments(kwargs):
    with pytest.raises(ValueError):
        search_cases(settings=KEY, client=fake_client(respond([])), **kwargs)
