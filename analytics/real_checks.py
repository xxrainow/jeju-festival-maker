"""B가 만든 실제 확인 도구 모음. A의 가짜 도구와 바꿔 끼운다.

    from agent.fake_checks import FAKE_TOOLS
    from analytics.real_checks import REAL_TOOLS
    tools = {**FAKE_TOOLS, **REAL_TOOLS}

표 만들기 (원자료가 있는 PC에서 한 번):
    uv run python -m analytics.weather
    uv run python -m analytics.real_checks --build
"""

import argparse

from analytics.check_budget import check_budget
from analytics.check_risk import check_risk
from analytics.check_target import check_target
from analytics.check_timing import check_timing
from analytics.check_venue import check_venue

REAL_TOOLS = {
    "check_timing": check_timing,
    "check_venue": check_venue,
    "check_target": check_target,
    "check_risk": check_risk,
    "check_budget": check_budget,
}


def build() -> None:
    from analytics import check_target as ct
    from analytics import check_venue as cv
    from analytics.area_link import load_bus_stations
    from analytics.boundary import load_jeju_boundaries
    from analytics.check_timing import build as build_timing
    from analytics.loaders import load_bus_usage, load_wifi_users
    from analytics.periods import RECENT_PERIOD
    from analytics.reference_data import admin_places, load_wifi_usage_agg

    build_timing()
    places = admin_places()
    demo = ct.build_demographics(load_wifi_users(), places)
    demo.to_csv(ct.DEMOGRAPHICS_PATH, index=False, encoding="utf-8-sig")
    print(f"\n## 성·연령 표: {demo['admin_area'].nunique()}개 동네 ({demo['source'].iloc[0]})")

    venue = cv.build_places(load_wifi_usage_agg(), places)
    venue.to_csv(cv.PLACES_PATH, index=False, encoding="utf-8-sig")
    bus = load_bus_usage(start=RECENT_PERIOD.start_date, end=RECENT_PERIOD.end_date)
    stations = cv.build_station_daily(bus.data, load_bus_stations())
    stations.to_csv(cv.STATIONS_PATH, index=False, encoding="utf-8-sig")
    cv.build_neighbors(load_jeju_boundaries()).to_csv(
        cv.NEIGHBORS_PATH, index=False, encoding="utf-8-sig"
    )
    print(
        f"## 장소 {len(venue):,}곳 (사용량 하위 25% {venue['small'].sum():,}곳 제외 대상), "
        f"정류소 {len(stations):,}곳 (이용 자료 없음 {stations['daily_users'].isna().sum():,}곳), "
        f"정류소 하루 이용 중앙값 {stations['daily_users'].median():,.0f}명"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="확인 도구 5개용 표 만들기")
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args(argv)
    if args.build:
        build()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
