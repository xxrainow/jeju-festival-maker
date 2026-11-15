"""Git에 올리는 와이파이 가공본 (analytics/reference/).

원자료가 없는 PC(팀원, 센터)도 확인 도구를 돌릴 수 있게, 공개 데이터(제주데이터허브)로 만든 가공본을 커밋한다.
코드는 reference를 먼저 읽고, 없으면 data/processed/(직접 만든 것)를 읽는다.

- wifi_usage_by_place_month_type.parquet: 와이파이 장소 × 월 × 방문유형 데이터 사용량
  (analytics.build_wifi_usage 결과를 그대로 복사)
- area_link_wifi.csv: 와이파이 장소 → 행정동·읍면 연결과 장소 좌표(AP 좌표 평균).
  후보지 비교표·check_timing과 같은 방식(동 지역은 AP 좌표로 행정동 판정, 길·애매함은 집계 제외).
  data/processed/area_link_wifi.csv(연결 보고서, AP 좌표 판정 전 방식)와 다르다

만들기: uv run python -m analytics.reference_data
"""

import shutil
from pathlib import Path

import pandas as pd

REFERENCE_DIR = Path(__file__).parent / "reference"
PROCESSED_DIR = Path("data/processed")
WIFI_USAGE_NAME = "wifi_usage_by_place_month_type.parquet"
AREA_LINK_NAME = "area_link_wifi.csv"


def reference_first(name: str) -> Path:
    """reference에 있으면 그것, 없으면 data/processed."""
    ref = REFERENCE_DIR / name
    return ref if ref.exists() else PROCESSED_DIR / name


def load_wifi_usage_agg() -> pd.DataFrame:
    return pd.read_parquet(reference_first(WIFI_USAGE_NAME))


def build_area_link(place_names: pd.Series) -> pd.DataFrame:
    """와이파이 장소 → 행정동·읍면 + 반영 위치(placement) + AP 좌표 평균."""
    from analytics.area_link import (
        link_wifi_places,
        load_bus_stations,
        load_wifi_ap,
        mark_exclusions,
    )
    from analytics.boundary import load_jeju_boundaries
    from analytics.candidate_compare import placement

    ap = load_wifi_ap()
    totals = pd.DataFrame({"wifi_place_name": sorted(place_names.unique()), "users": 0})
    linked = mark_exclusions(
        link_wifi_places(totals, ap, load_bus_stations(), load_jeju_boundaries())
    )
    linked["placement"] = placement(linked)
    xy = ap[["place_key"]].assign(
        latitude=pd.to_numeric(ap["latitude"], errors="coerce"),
        longitude=pd.to_numeric(ap["longitude"], errors="coerce"),
    )
    coords = xy.groupby("place_key")[["latitude", "longitude"]].mean()
    linked = linked.join(coords, on="wifi_place_name")
    cols = ["wifi_place_name", "area", "area_level", "status", "candidates", "method",
            "category", "excluded_reason", "placement", "latitude", "longitude"]  # fmt: skip
    return linked[cols]


def load_area_link() -> pd.DataFrame:
    path = REFERENCE_DIR / AREA_LINK_NAME
    if path.exists():
        return pd.read_csv(path, encoding="utf-8-sig")
    usage = load_wifi_usage_agg()
    return build_area_link(usage["wifi_place_name"])


def admin_places(link: pd.DataFrame | None = None) -> pd.DataFrame:
    """행정동·읍면 표에 들어가는 장소만 (wifi_place_name, admin_area, latitude, longitude, category)."""
    from analytics.candidate_compare import ADMIN

    link = load_area_link() if link is None else link
    placed = link[link["placement"] == ADMIN]
    return placed.rename(columns={"area": "admin_area"})[
        ["wifi_place_name", "admin_area", "latitude", "longitude", "category"]
    ].reset_index(drop=True)


def main() -> None:
    from analytics.loaders import load_wifi_users

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    src = PROCESSED_DIR / WIFI_USAGE_NAME
    shutil.copyfile(src, REFERENCE_DIR / WIFI_USAGE_NAME)
    usage = pd.read_parquet(src)
    names = pd.concat([usage["wifi_place_name"], load_wifi_users()["wifi_place_name"]])
    link = build_area_link(names)
    link.to_csv(REFERENCE_DIR / AREA_LINK_NAME, index=False, encoding="utf-8-sig")
    for name in (WIFI_USAGE_NAME, AREA_LINK_NAME):
        size = (REFERENCE_DIR / name).stat().st_size
        print(f"{REFERENCE_DIR / name}: {size / 1024:,.0f} KB")
    print(link["placement"].value_counts().to_string())


if __name__ == "__main__":
    main()
