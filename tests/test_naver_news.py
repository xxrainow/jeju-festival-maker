from datetime import UTC, date, datetime

import httpx
import pytest

from app.settings import Settings
from research.collect_news import collect_news, latest_saved, load_cases, save_result
from research.naver_news import (
    NewsSearchError,
    clean_text,
    make_case_id,
    parse_pub_date,
    search_news,
    to_case,
)

# 네이버 응답 형식을 흉내 낸 가짜 기사. 실제 기사가 아니다.
ITEM_A = {
    "title": "○○군 <b>커피 축제</b> &quot;성황&quot;",
    "originallink": "https://example.com/news/1",
    "link": "https://n.news.naver.com/article/1",
    "description": "지역 농가가 참여한 <b>시음</b> 부스를   운영했다.",
    "pubDate": "Tue, 21 Oct 2026 09:30:00 +0900",
}
ITEM_B = {
    "title": "△△시 딸기 축제",
    "originallink": "",
    "link": "https://example.com/news/2",
    "description": "체험 프로그램 운영",
    "pubDate": "잘못된 날짜",
}
ITEM_NO_URL = {"title": "링크 없음", "originallink": "", "link": "", "description": ""}

KEYS = Settings(naver_client_id="test-id", naver_client_secret="test-secret")
NO_KEYS = Settings(naver_client_id="", naver_client_secret="", _env_file=None)
NOW = datetime(2026, 11, 6, 5, 30, tzinfo=UTC)


def fake_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def respond(items, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"items": items})

    return handler


def test_clean_text_removes_tags_and_entities():
    assert clean_text(ITEM_A["title"]) == '○○군 커피 축제 "성황"'
    assert clean_text(ITEM_A["description"]) == "지역 농가가 참여한 시음 부스를 운영했다."


def test_parse_pub_date():
    assert parse_pub_date(ITEM_A["pubDate"]) == date(2026, 10, 21)
    assert parse_pub_date("잘못된 날짜") is None
    assert parse_pub_date("") is None


def test_case_id_is_stable():
    assert make_case_id("https://example.com/news/1") == make_case_id("https://example.com/news/1")
    assert make_case_id("https://example.com/news/1") != make_case_id("https://example.com/news/2")


def test_to_case_matches_contract():
    case = to_case(ITEM_A, NOW)
    assert case.title == '○○군 커피 축제 "성황"'
    assert str(case.source_url) == "https://example.com/news/1"  # 원문 링크를 우선
    assert case.published_at == date(2026, 10, 21)
    assert case.event_date is None
    assert case.retrieved_at == NOW
    assert case.evidence_status == "snippet_only"


def test_to_case_falls_back_to_link_and_skips_bad_items():
    case = to_case(ITEM_B, NOW)
    assert str(case.source_url) == "https://example.com/news/2"
    assert case.published_at is None  # 날짜를 읽지 못하면 추측하지 않는다
    assert to_case(ITEM_NO_URL, NOW) is None
    assert to_case({**ITEM_A, "originallink": "주소 아님"}, NOW) is None


def test_search_sends_keys_and_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url.copy_with(query=None))
        seen["headers"] = request.headers
        seen["params"] = request.url.params
        return httpx.Response(200, json={"items": [ITEM_A, ITEM_NO_URL]})

    cases = search_news("커피 축제", display=5, settings=KEYS, client=fake_client(handler))
    assert len(cases) == 1
    assert seen["url"] == "https://naverapihub.apigw.ntruss.com/search/v1/news"
    assert seen["headers"]["X-NCP-APIGW-API-KEY-ID"] == "test-id"
    assert seen["headers"]["X-NCP-APIGW-API-KEY"] == "test-secret"
    assert seen["params"]["query"] == "커피 축제"
    assert seen["params"]["display"] == "5"
    assert seen["params"]["sort"] == "date"


def test_missing_keys_raise_clear_error():
    with pytest.raises(NewsSearchError, match="NAVER_CLIENT_ID"):
        search_news("축제", settings=NO_KEYS, client=fake_client(respond([])))


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_error_message_hides_keys(status):
    with pytest.raises(NewsSearchError) as exc:
        search_news("축제", settings=KEYS, client=fake_client(respond([], status)))
    assert f"HTTP {status}" in str(exc.value)
    assert "test-secret" not in str(exc.value)


def test_network_error_is_wrapped():
    def handler(request):
        raise httpx.ConnectError("연결 실패")

    with pytest.raises(NewsSearchError, match="연결"):
        search_news("축제", settings=KEYS, client=fake_client(handler))


def test_broken_response_is_rejected():
    def handler(request):
        return httpx.Response(200, json={"wrong": []})

    with pytest.raises(NewsSearchError, match="기사 목록"):
        search_news("축제", settings=KEYS, client=fake_client(handler))


@pytest.mark.parametrize(
    "kwargs", [{"query": " "}, {"query": "축제", "display": 0}, {"query": "축제", "sort": "x"}]
)
def test_invalid_arguments(kwargs):
    with pytest.raises(ValueError):
        search_news(settings=KEYS, client=fake_client(respond([])), **kwargs)


def test_collect_merges_duplicates_across_queries():
    client = fake_client(respond([ITEM_A, ITEM_B, ITEM_A]))
    result = collect_news(["커피 축제", "딸기 축제"], settings=KEYS, client=client)
    assert result["status"] == "success"
    assert result["case_count"] == 2
    case_a = make_case_id("https://example.com/news/1")
    assert result["queries_by_case"][case_a] == ["커피 축제", "딸기 축제"]


def test_collect_keeps_going_when_one_query_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["query"] == "실패":
            return httpx.Response(500)
        return httpx.Response(200, json={"items": [ITEM_A]})

    result = collect_news(["실패", "커피 축제"], settings=KEYS, client=fake_client(handler))
    assert result["status"] == "partial"
    assert result["case_count"] == 1
    assert result["errors"][0]["query"] == "실패"

    failed = collect_news(["실패"], settings=KEYS, client=fake_client(handler))
    assert failed["status"] == "failed"


def test_saved_result_round_trips(tmp_path):
    assert latest_saved(tmp_path) is None
    result = collect_news(["커피 축제"], settings=KEYS, client=fake_client(respond([ITEM_A])))
    path = save_result(result, tmp_path)
    assert latest_saved(tmp_path) == path
    cases = load_cases(path)
    assert [c.case_id for c in cases] == [make_case_id("https://example.com/news/1")]
