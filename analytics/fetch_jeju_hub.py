"""제주데이터허브 API 4종을 페이지 단위로 받아 data/raw/에 CSV로 저장한다.

실행:
    uv run python -m analytics.fetch_jeju_hub --check   # API마다 첫 페이지만 확인
    uv run python -m analytics.fetch_jeju_hub           # 전체 수집
    uv run python -m analytics.fetch_jeju_hub --only bus_stations

키는 .env의 JEJU_HUB_KEY에서 읽고, 화면·오류 메시지에 출력하지 않는다.
"""

import argparse
import logging
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx
import pandas as pd

from app.settings import Settings

BASE_URL = "https://open.jejudatahub.net/api/proxy"
PAGE_SIZE = 100
DAILY_CALL_LIMIT = 1_000
OUTPUT_DIR = Path("data/raw")

# 요청 주소에 키가 들어가므로 httpx 요청 로그를 끈다
logging.getLogger("httpx").setLevel(logging.WARNING)


@dataclass(frozen=True)
class Dataset:
    name: str
    title: str
    api_id: str
    params: dict[str, str] = field(default_factory=dict)

    @property
    def output_path(self) -> Path:
        return OUTPUT_DIR / f"jejuhub_{self.name}.csv"


def datasets(ap_base_date: str) -> dict[str, Dataset]:
    items = [
        Dataset("bus_stations", "버스 정류소 기본 정보", "DD11ab6a6t11D16baaa1a2tD26ata161"),
        Dataset(
            "wifi_ap",
            "공공와이파이 AP 정보",
            "Dtb18ta1btbD1Da1a81aaDttab6tDabb",
            {"baseDate": ap_base_date},
        ),
        Dataset("lodging", "관광 숙박업 정보", "ttbttaD3aaa3ta8bbtDtaDD18t37aD17"),
        Dataset(
            "tourist_spot_visitors",
            "관광지별 내국인 유입자 수",
            "bt11Daa5at1tat515DDtaa9D5aa99t11",
            {"startDate": "202201", "endDate": "202412"},
        ),
    ]
    return {d.name: d for d in items}


class HubError(RuntimeError):
    pass


class HubClient:
    def __init__(self, key: str, client: httpx.Client | None = None):
        if not key:
            raise HubError(".env에 JEJU_HUB_KEY가 비어 있습니다")
        self._key = key
        self._client = client or httpx.Client(timeout=30)
        self.calls: dict[str, int] = {}

    def _mask(self, text: str) -> str:
        return text.replace(self._key, "***")

    def get_page(self, dataset: Dataset, number: int) -> dict:
        used = self.calls.get(dataset.name, 0)
        if used >= DAILY_CALL_LIMIT:
            raise HubError(f"{dataset.title}: 하루 호출 한도 {DAILY_CALL_LIMIT}회에 도달했습니다")
        self.calls[dataset.name] = used + 1

        url = f"{BASE_URL}/{dataset.api_id}/{self._key}"
        params = {**dataset.params, "number": number, "limit": PAGE_SIZE}
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            # 예외 메시지와 traceback에 키가 든 주소가 남지 않게 새 예외로 바꾼다
            raise HubError(f"{dataset.title}: 요청 실패 ({self._mask(str(error))})") from None
        if not isinstance(body, dict) or "data" not in body:
            raise HubError(f"{dataset.title}: 예상과 다른 응답 ({self._mask(str(body))[:200]})")
        return body


def check_first_page(dataset: Dataset, body: dict) -> int:
    """첫 페이지가 limit만큼(전체가 적으면 전체) 왔는지 확인하고 예상 호출 수를 돌려준다."""
    total = int(body.get("totCnt") or 0)
    received = len(body["data"])
    expected = min(PAGE_SIZE, total)
    if received != expected:
        raise HubError(
            f"{dataset.title}: 첫 페이지 {received}건 (기대 {expected}건, 전체 {total}건). "
            "limit 파라미터가 적용되지 않았을 수 있어 중단합니다"
        )
    return max(1, math.ceil(total / PAGE_SIZE))


def fetch(hub: HubClient, dataset: Dataset, check_only: bool = False) -> pd.DataFrame | None:
    first = hub.get_page(dataset, 1)
    pages = check_first_page(dataset, first)
    print(
        f"[{dataset.title}] 전체 {first.get('totCnt')}건, 첫 페이지 {len(first['data'])}건, "
        f"예상 호출 {pages}회"
    )
    if pages > DAILY_CALL_LIMIT:
        raise HubError(f"{dataset.title}: 예상 호출 {pages}회가 하루 한도를 넘어 중단합니다")
    if check_only:
        return None

    rows = list(first["data"])
    body, number = first, 1
    while body.get("hasMore"):
        number += 1
        body = hub.get_page(dataset, number)
        rows.extend(body["data"])

    print(f"[{dataset.title}] {len(rows)}건 수집, 호출 {hub.calls[dataset.name]}회")
    # 빈 칸이 섞인 정수 열이 소수로 바뀌지 않게 응답값을 그대로 둔다
    return pd.DataFrame(rows, dtype=object)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="제주데이터허브 API 수집")
    parser.add_argument("--check", action="store_true", help="API마다 첫 페이지만 확인")
    parser.add_argument("--only", nargs="+", help="받을 데이터 이름")
    parser.add_argument(
        "--ap-base-date",
        default=date.today().strftime("%Y%m%d"),
        help="공공와이파이 AP 정보 기준일 (YYYYMMDD)",
    )
    args = parser.parse_args(argv)

    targets = datasets(args.ap_base_date)
    names = args.only or list(targets)
    unknown = set(names) - set(targets)
    if unknown:
        parser.error(f"알 수 없는 데이터: {', '.join(sorted(unknown))}")

    hub = HubClient(Settings().jeju_hub_key.get_secret_value())
    try:
        for name in names:
            dataset = targets[name]
            df = fetch(hub, dataset, check_only=args.check)
            if df is not None:
                dataset.output_path.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(dataset.output_path, index=False, encoding="utf-8-sig")
                print(f"[{dataset.title}] 저장: {dataset.output_path}")
    except HubError as error:
        raise SystemExit(f"중단: {error}") from None
    finally:
        for name, count in hub.calls.items():
            print(f"호출 횟수 {targets[name].title}: {count}회 (하루 한도 {DAILY_CALL_LIMIT}회)")


if __name__ == "__main__":
    main()
