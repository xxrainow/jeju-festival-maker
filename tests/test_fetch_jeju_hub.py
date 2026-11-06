import httpx
import pytest

from analytics import fetch_jeju_hub
from analytics.fetch_jeju_hub import HubClient, HubError, datasets, fetch

KEY = "secret-test-key"
DATASET = datasets("20261101")["bus_stations"]


def fake_hub(total: int, page_size: int = 100, status: int = 200):
    """totCnt=total인 데이터를 number/limit로 나눠 주는 가짜 허브."""
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if status != 200:
            return httpx.Response(status, request=request)
        number = int(request.url.params["number"])
        start = (number - 1) * page_size
        data = [{"id": i} for i in range(start, min(start + page_size, total))]
        body = {"totCnt": total, "hasMore": start + page_size < total, "data": data}
        return httpx.Response(200, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HubClient(KEY, client), requests


def test_fetch_follows_has_more_with_number_and_limit():
    hub, requests = fake_hub(total=250)
    df = fetch(hub, DATASET)
    assert len(df) == 250
    assert hub.calls == {"bus_stations": 3}
    assert [r.url.params["number"] for r in requests] == ["1", "2", "3"]
    assert {r.url.params["limit"] for r in requests} == {"100"}


def test_dataset_params_are_sent():
    hub, requests = fake_hub(total=5)
    fetch(hub, datasets("20261101")["tourist_spot_visitors"])
    params = requests[0].url.params
    assert (params["startDate"], params["endDate"]) == ("202201", "202412")


def test_check_only_makes_one_call():
    hub, _ = fake_hub(total=250)
    assert fetch(hub, DATASET, check_only=True) is None
    assert hub.calls == {"bus_stations": 1}


def test_stops_when_first_page_is_not_limit_size():
    hub, _ = fake_hub(total=250, page_size=10)
    with pytest.raises(HubError, match="첫 페이지 10건"):
        fetch(hub, DATASET)
    assert hub.calls == {"bus_stations": 1}


def test_small_dataset_first_page_is_accepted():
    hub, _ = fake_hub(total=7)
    assert len(fetch(hub, DATASET)) == 7


def test_stops_when_expected_calls_exceed_daily_limit():
    hub, _ = fake_hub(total=100 * 1_000 + 1)
    with pytest.raises(HubError, match="하루 한도"):
        fetch(hub, DATASET)


def test_key_not_in_error_message():
    hub, _ = fake_hub(total=0, status=500)
    with pytest.raises(HubError) as error:
        fetch(hub, DATASET)
    assert KEY not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


def test_empty_key_is_rejected():
    with pytest.raises(HubError, match="JEJU_HUB_KEY"):
        HubClient("")


def test_key_not_printed(monkeypatch, tmp_path, capsys):
    hub, _ = fake_hub(total=3)
    monkeypatch.setattr(fetch_jeju_hub, "HubClient", lambda key: hub)
    monkeypatch.setattr(fetch_jeju_hub, "OUTPUT_DIR", tmp_path)
    fetch_jeju_hub.main(["--only", "bus_stations"])
    out = capsys.readouterr().out
    assert KEY not in out
    assert "호출 횟수 버스 정류소 기본 정보: 1회" in out
    assert (tmp_path / "jejuhub_bus_stations.csv").exists()


def test_integer_columns_with_blanks_stay_integers():
    def handler(request):
        data = [{"name": "a", "roomCount": 61}, {"name": "b", "roomCount": None}]
        return httpx.Response(200, json={"totCnt": 2, "hasMore": False, "data": data})

    hub = HubClient(KEY, httpx.Client(transport=httpx.MockTransport(handler)))
    df = fetch(hub, DATASET)
    assert df.to_csv(index=False) == "name,roomCount\na,61\nb,\n"
