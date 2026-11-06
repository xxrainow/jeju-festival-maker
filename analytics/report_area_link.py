"""정류소·와이파이 장소의 읍면동 연결 결과를 만들고 매칭률을 보고한다.

실행: uv run python -m analytics.report_area_link [--start 202301 --end 202510] [--groups 묶음.json]
묶음 파일 형식: {"묶음 이름": ["제주시 일도1동", "제주시 일도2동", ...], ...}
결과: data/processed/area_link_bus.csv, data/processed/area_link_wifi.csv
"""

import argparse
import json
import numbers
from pathlib import Path

import pandas as pd

from analytics.area_link import (
    AMBIGUOUS,
    LINKED,
    NO_ADDRESS,
    NOT_FOUND,
    AreaGroup,
    area_totals,
    assign_groups,
    candidate_city,
    link_bus_usage,
    link_wifi_places,
    load_bus_stations,
    load_wifi_ap,
    mark_exclusions,
    match_summary,
    nearest_area_reference,
)
from analytics.loaders import load_bus_usage, load_wifi_users
from analytics.periods import CANDIDATE_PERIOD, analysis_period

OUTPUT_DIR = Path("data/processed")
TOP_N = 20


def _cell(value) -> str:
    if isinstance(value, numbers.Integral):
        return f"{value:,}"
    if isinstance(value, numbers.Real):
        return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"
    return str(value)


def table(df: pd.DataFrame) -> str:
    header = "| " + " | ".join(map(str, df.columns)) + " |"
    rule = "|" + "---|" * len(df.columns)
    rows = ["| " + " | ".join(_cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, rule, *rows])


def summary_table(linked: pd.DataFrame) -> str:
    s = match_summary(linked).reset_index()
    s.columns = ["상태", "장소 수", "이용자 수", "장소 비율(%)", "이용자 비율(%)"]
    return table(s)


def unmatched_city_table(linked: pd.DataFrame, city: pd.Series) -> str:
    """시별 연결·미연결 이용자 비중. 미연결이 한 시에 몰렸는지 본다."""
    df = linked.assign(city=city)
    df["구분"] = df["status"].where(df["status"] == LINKED, "미연결")
    pivot = df.pivot_table(index="city", columns="구분", values="users", aggfunc="sum").fillna(0)
    for col in (LINKED, "미연결"):
        if col not in pivot:
            pivot[col] = 0
        pivot[f"{col} 비중(%)"] = pivot[col] / pivot[col].sum() * 100
    out = pivot.reset_index().rename(columns={"city": "시"})
    return table(out[["시", LINKED, "미연결", f"{LINKED} 비중(%)", "미연결 비중(%)"]])


def load_groups(path: Path) -> list[AreaGroup]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [AreaGroup(name, frozenset(dongs)) for name, dongs in data.items()]


def aggregation_section(
    linked: pd.DataFrame, groups: list[AreaGroup]
) -> tuple[pd.DataFrame, list[str]]:
    """동네별 집계 제외 요약과 후보지 묶음 합계."""
    linked = mark_exclusions(linked)
    _, excluded = area_totals(linked)
    excluded.columns = ["제외 사유", "장소 수", "이용자 수"]
    lines = ["### 동네별 집계에서 뺀 항목", table(excluded) if len(excluded) else "없음"]
    if groups:
        linked = assign_groups(linked, groups)
        totals, _ = area_totals(linked, by="group")
        boundary = (
            linked[linked["group_method"].eq("경계 묶음") & linked["excluded_reason"].isna()]
            .groupby("group")["users"]
            .agg(["size", "sum"])
        )
        totals = totals.merge(boundary, how="left", left_on="group", right_index=True).fillna(0)
        totals.columns = [
            "묶음",
            "장소 수",
            "이용자 수",
            "경계 묶음 장소 수",
            "경계 묶음 이용자 수",
        ]
        lines += ["### 후보지 묶음 합계", table(totals)]
    return linked, lines


def bus_report(period, groups: list[AreaGroup]) -> list[str]:
    stations = load_bus_stations()
    bus = load_bus_usage(start=period.start_date, end=period.end_date)
    totals = (
        bus.data.groupby("station_key", as_index=False)["user_count"]
        .sum()
        .rename(columns={"user_count": "users"})
    )
    if totals["users"].sum() != bus.data["user_count"].sum():
        raise ValueError("정류소별 합계가 원자료 합계와 다릅니다")
    linked = link_bus_usage(totals, stations)

    ref = nearest_area_reference(linked, stations)
    linked["nearest_area_ref"] = ref
    linked["city"] = linked["area"].fillna("").map(candidate_city)
    ambiguous = linked["status"] == AMBIGUOUS
    linked.loc[ambiguous, "city"] = linked.loc[ambiguous, "candidates"].map(candidate_city)
    no_address = linked["status"] == NO_ADDRESS
    linked.loc[no_address, "city"] = (
        linked.loc[no_address, "nearest_area_ref"].fillna("").map(candidate_city)
    )
    linked, aggregation = aggregation_section(linked, groups)
    linked.to_csv(OUTPUT_DIR / "area_link_bus.csv", index=False, encoding="utf-8-sig")

    unmatched = linked[linked["status"] != LINKED]
    top = unmatched.nlargest(TOP_N, "users")[["station_key", "users", "status", "candidates"]]
    top = top.assign(참고=unmatched.loc[top.index, "nearest_area_ref"].fillna(""))
    top.columns = ["정류소", "이용자 수", "상태", "후보 읍면동", "좌표 최근접 지역(참고)"]

    na_area = (
        linked[no_address]
        .groupby("nearest_area_ref")["users"]
        .agg(["size", "sum"])
        .sort_values("sum", ascending=False)
        .head(10)
        .reset_index()
    )
    na_area.columns = ["좌표 최근접 지역(참고)", "정류소 수", "이용자 수"]

    return [
        f"## 버스 정류소 ({period.label()}, 이용자 = 승하차 인원 합계)",
        f"정류소 {len(linked):,}곳, 이상일 {len(bus.excluded_dates)}일 제외. 연결 단위는 행정동·읍면.",
        "### 매칭률",
        summary_table(linked),
        f"### 연결 안 된 정류소 이용자 상위 {TOP_N}",
        table(top),
        "### 지역 쏠림 (애매함은 후보 시, 주소 없음은 좌표 최근접 시 기준, 이름 없음은 알 수 없음)",
        unmatched_city_table(linked, linked["city"]),
        "### 주소 없는 정류소의 좌표 최근접 지역 상위 10 (참고)",
        table(na_area),
        *aggregation,
    ]


def wifi_report(period, groups: list[AreaGroup]) -> list[str]:
    stations = load_bus_stations()
    users = period.filter_months(load_wifi_users())
    totals = (
        users.groupby("wifi_place_name", as_index=False)["user_count"]
        .sum()
        .rename(columns={"user_count": "users"})
    )
    linked = link_wifi_places(totals, load_wifi_ap(), stations)
    linked["city"] = linked["area"].fillna("").map(candidate_city)
    ambiguous = linked["status"] == AMBIGUOUS
    linked.loc[ambiguous, "city"] = linked.loc[ambiguous, "candidates"].map(candidate_city)
    linked, aggregation = aggregation_section(linked, groups)
    linked.to_csv(OUTPUT_DIR / "area_link_wifi.csv", index=False, encoding="utf-8-sig")

    method = (
        linked.groupby(["status", "method"], dropna=False)
        .agg(places=("users", "size"), users=("users", "sum"))
        .reset_index()
        .fillna({"method": "-"})
    )
    method.columns = ["상태", "연결 방법", "장소 수", "이용자 수"]

    unmatched = linked[linked["status"] != LINKED]
    top = unmatched.nlargest(TOP_N, "users")[
        ["wifi_place_name", "users", "status", "category", "candidates"]
    ]
    top.columns = ["장소", "이용자 수", "상태", "유형", "후보 읍면동"]

    category = (
        linked.assign(구분=linked["status"].where(linked["status"] == LINKED, "미연결"))
        .pivot_table(index="category", columns="구분", values="users", aggfunc="sum")
        .fillna(0)
    )
    category["미연결 비율(%)"] = category["미연결"] / category.sum(axis=1) * 100
    category = category.reset_index().rename(columns={"category": "유형"})

    levels = linked[linked["status"] == LINKED].groupby("area_level")["users"].agg(["size", "sum"])
    levels = levels.reset_index()
    levels.columns = ["연결 단위", "장소 수", "이용자 수"]

    return [
        f"## 와이파이 장소 ({period.label()}, 이용자 = 월별 사용자 수 합계)",
        f"장소 {len(linked):,}곳. AP 정보 기준일 2022-12-25.",
        "### 매칭률",
        summary_table(linked),
        table(method),
        "### 연결 단위 (법정동은 행정동 매핑표 확보 후 변환 필요)",
        table(levels),
        f"### 연결 안 된 장소 이용자 상위 {TOP_N}",
        table(top),
        "### 지역 쏠림 (애매함은 후보 시 기준, 이름 없음은 알 수 없음)",
        unmatched_city_table(linked, linked["city"]),
        "### 장소 유형별 미연결 비율",
        table(category),
        *aggregation,
    ]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="읍면동 연결 매칭률 보고")
    parser.add_argument("--start", help="시작 월 YYYYMM")
    parser.add_argument("--end", help="끝 월 YYYYMM")
    parser.add_argument("--groups", type=Path, help="후보지 행정동 묶음 JSON")
    args = parser.parse_args(argv)
    period = analysis_period(args.start, args.end, default=CANDIDATE_PERIOD)
    groups = load_groups(args.groups) if args.groups else []

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = bus_report(period, groups) + wifi_report(period, groups)
    print("\n\n".join(lines))
    print(f"\n상태 값: {LINKED}, {AMBIGUOUS}, {NO_ADDRESS}, {NOT_FOUND}")


if __name__ == "__main__":
    main()
