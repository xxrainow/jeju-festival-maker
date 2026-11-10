"""동네(행정동·읍면)별 월별 외지인 방문 지수 (check_timing용).

지수 = 그 달 값 ÷ 12개월 평균. 1보다 크면 그 동네의 연평균보다 외지인이 많은 달이다.

자료 우선순위:
1. 4-11 내국인 유동인구 실데이터: 거주지 "그외"의 방문인구, 12개월 이상 있을 때만
2. 와이파이 관광 사용량 (대체 지표): 사람 수가 아니라 데이터 사용량이다

4-11 가짜 데이터(2주)로는 연평균을 구할 수 없어 와이파이를 쓴다.

실행: uv run python -m analytics.check_timing --build  (이 파일의 표도 함께 만든다)
결과: data/processed/outsider_index.csv
"""

from pathlib import Path

import pandas as pd

from analytics.periods import COMPARISON_PERIOD, AnalysisPeriod

OUTPUT_PATH = Path("data/processed/outsider_index.csv")
WIFI_USAGE_AGG_PATH = Path("data/processed/wifi_usage_by_place_month_type.parquet")
TOURISM_VISIT_TYPE = "관광"
OUTSIDER_RESIDENCE = "그외"
MIN_FLOW_MONTHS = 12
# 그 달 집계에 들어간 장소 수가 가장 많은 달의 이 비율보다 적으면 경고 (AP 설치·철거로 값이 흔들림)
PLACE_COUNT_DROP = 0.8

WIFI_SOURCE = "와이파이 관광 사용량 기준(외지인 방문 대체 지표)"
FLOW_SOURCE = "4-11 내국인 유동인구(읍면동) 거주지 그외 방문인구"
COLUMNS = ["admin_area", "month", "index", "value", "places", "source", "is_synthetic"]


def _index_table(monthly: pd.DataFrame, source: str, is_synthetic: bool) -> pd.DataFrame:
    """monthly: admin_area, month(1~12), value, places. 12개월이 다 있는 동네만 지수를 낸다."""
    full = monthly.groupby("admin_area")["month"].transform("nunique") == 12
    out = monthly[full].copy()
    mean = out.groupby("admin_area")["value"].transform("mean")
    out["index"] = (out["value"] / mean).where(mean > 0)
    out["source"] = source
    out["is_synthetic"] = is_synthetic
    return out[COLUMNS].sort_values(["admin_area", "month"]).reset_index(drop=True)


def wifi_place_areas(place_names: pd.Series) -> pd.DataFrame:
    """와이파이 장소 → 행정동·읍면. 후보지 비교표와 같은 연결(AP 좌표 판정, 길·애매함 제외)."""
    from analytics.area_link import (
        link_wifi_places,
        load_bus_stations,
        load_wifi_ap,
        mark_exclusions,
    )
    from analytics.boundary import load_jeju_boundaries
    from analytics.candidate_compare import ADMIN, placement

    totals = pd.DataFrame({"wifi_place_name": place_names.unique(), "users": 0})
    linked = mark_exclusions(
        link_wifi_places(totals, load_wifi_ap(), load_bus_stations(), load_jeju_boundaries())
    )
    placed = linked[placement(linked) == ADMIN]
    return placed[["wifi_place_name", "area"]].rename(columns={"area": "admin_area"})


def wifi_outsider_index(
    usage: pd.DataFrame,
    place_areas: pd.DataFrame,
    period: AnalysisPeriod = COMPARISON_PERIOD,
) -> pd.DataFrame:
    """와이파이 관광 사용량으로 동네 × 월 지수. 기간 안 같은 달끼리 평균한 뒤 12개월 평균으로 나눈다."""
    u = period.filter_months(usage)
    u = u[u["visit_type"] == TOURISM_VISIT_TYPE].merge(place_areas, on="wifi_place_name")
    u = u.assign(
        year=u["base_year_month"].str[:4],
        month=u["base_year_month"].str[4:].astype(int),
        use_amount=u["use_amount"].astype(float),
    )
    by_ym = u.groupby(["admin_area", "year", "month"]).agg(
        value=("use_amount", "sum"), places=("wifi_place_name", "nunique")
    )
    monthly = by_ym.groupby(["admin_area", "month"]).mean().reset_index()
    source = f"{WIFI_SOURCE} {period.label()}"
    return _index_table(monthly, source, is_synthetic=False)


def flow_outsider_index(flow: pd.DataFrame, is_synthetic: bool) -> pd.DataFrame | None:
    """4-11 유동인구(검사를 통과한 data)로 동네 × 월 지수. 12개월이 안 되면 None.

    달마다 날 수가 달라 일평균 방문인구로 비교한다.
    """
    f = flow[flow["resd"] == OUTSIDER_RESIDENCE]
    dates = f["base_date"]  # validate_flow를 거치면 날짜형, 원본 문자열이면 YYYYMMDD
    if not pd.api.types.is_datetime64_any_dtype(dates):
        dates = pd.to_datetime(dates.astype(str), format="%Y%m%d")
    if dates.dt.to_period("M").nunique() < MIN_FLOW_MONTHS:
        return None
    f = f.assign(
        month=dates.dt.month,
        ym=dates.dt.to_period("M"),
        date=dates,
        value=pd.to_numeric(f["visit_pop_cnt"], errors="coerce"),
    )
    daily = f.groupby(["emd_nm", "ym", "month", "date"])["value"].sum().reset_index()
    by_ym = daily.groupby(["emd_nm", "ym", "month"])["value"].mean().reset_index()
    monthly = (
        by_ym.groupby(["emd_nm", "month"])["value"]
        .mean()
        .reset_index()
        .rename(columns={"emd_nm": "admin_area"})
        .assign(places=pd.NA)
    )
    start, end = dates.min().strftime("%Y-%m"), dates.max().strftime("%Y-%m")
    return _index_table(monthly, f"{FLOW_SOURCE} {start}~{end}", is_synthetic)


def choose_index(flow_index: pd.DataFrame | None, wifi_index: pd.DataFrame) -> pd.DataFrame:
    """4-11 지수가 있는 동네는 그것을, 없는 동네는 와이파이 지수를 쓴다."""
    if flow_index is None or flow_index.empty:
        return wifi_index
    rest = wifi_index[~wifi_index["admin_area"].isin(flow_index["admin_area"])]
    return pd.concat([flow_index, rest], ignore_index=True)


def place_count_warning(rows: pd.DataFrame) -> str | None:
    """그 동네 장소 수가 달마다 크게 다르면 경고 문장."""
    places = pd.to_numeric(rows["places"], errors="coerce").dropna()
    if places.empty or places.min() >= places.max() * PLACE_COUNT_DROP:
        return None
    return (
        f"와이파이 장소 수가 달마다 달라요 (최소 {places.min():.0f}곳, 최대 {places.max():.0f}곳). "
        "AP 설치·철거 때문에 지수가 흔들릴 수 있어요."
    )
