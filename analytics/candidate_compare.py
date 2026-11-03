"""후보지 비교표: 행정동·읍면 단위로 지표를 한 표에 모은다.

실행: uv run python -m analytics.candidate_compare [--start 202301 --end 202412]
결과: data/processed/candidate_compare.csv (행정동·읍면),
      data/processed/candidate_compare_legal_dong.csv (행정동으로 바꾸지 못한 법정동 자료),
      data/processed/legal_admin_mapping.csv (법정동 → 행정동 변환표)

- 월평균은 기간 합계 ÷ 기간 개월 수. 관광지는 자료가 있는 달만으로 평균한다
- 동 지역 와이파이는 AP 좌표로 행정동 판정, 숙박업은 법정동 → 행정동 변환표로 바꾼다
- 애매함, 주소 없음, 이름 없음, 집계 제외 항목은 표에 넣지 않고 지표별 반영 현황에 남긴다
"""

import argparse
from pathlib import Path

import pandas as pd

from analytics.area_link import (
    AMBIGUOUS,
    LINKED,
    NOT_FOUND,
    area_level,
    link_bus_usage,
    link_wifi_places,
    load_bus_stations,
    load_wifi_ap,
    mark_exclusions,
    parse_area,
)
from analytics.boundary import load_jeju_boundaries
from analytics.dong_mapping import build_pair_mapping, collect_pairs, convert_legal_to_admin
from analytics.loaders import load_bus_usage, load_festivals, load_wifi_users
from analytics.periods import COMPARISON_PERIOD, AnalysisPeriod, analysis_period
from analytics.report_area_link import table
from analytics.tourist_spots import (
    METHOD_MULTI,
    load_spot_areas,
    load_spot_table,
    load_tourist_spot_visitors,
)

LODGING_PATH = Path("data/raw/jejuhub_lodging.csv")
WIFI_USAGE_AGG_PATH = Path("data/processed/wifi_usage_by_place_month_type.parquet")
OUTPUT_DIR = Path("data/processed")

FESTIVAL_YEAR = 2026
LONG_EVENT_DAYS = 30
OPEN_STATUS = "영업/정상"
TOURISM_VISIT_TYPE = "관광"
# 개최 장소가 여러 동에 걸쳐 한 동에 붙일 수 없는 축제
MULTI_AREA_FESTIVALS = {
    "2026 제주 국가유산 방문의 해": "제주특별자치도 전역 (국가유산 100개소)",
    "제15회 서귀포 봄맞이축제 개최": "서귀진지·서복전시관·가시리 날짜별로 다른 장소",
}

ADMIN, LEGAL, AMBIG, EXCLUDED, UNPLACED = (
    "행정동·읍면 표",
    "법정동 표 (변환 못 함)",
    "애매함",
    "집계 제외",
    "위치 미연결",
)
PLACEMENTS = [ADMIN, LEGAL, AMBIG, EXCLUDED, UNPLACED]


def months_in(period: AnalysisPeriod) -> int:
    start, end = period.start_date, period.end_date
    return (end.year - start.year) * 12 + end.month - start.month + 1


def placement(linked: pd.DataFrame) -> pd.Series:
    """행마다 어느 표에 들어가는지: 행정동·읍면 표, 법정동 표, 애매함, 집계 제외, 위치 미연결."""
    excluded = (
        linked["excluded_reason"].notna()
        if "excluded_reason" in linked
        else pd.Series(False, index=linked.index)
    )
    linked_ok = linked["status"].eq(LINKED) & ~excluded
    out = pd.Series(UNPLACED, index=linked.index)
    out[linked["status"].eq(AMBIGUOUS)] = AMBIG
    out[excluded] = EXCLUDED
    out[linked_ok & linked["area_level"].isin(["행정동", "읍면"])] = ADMIN
    out[linked_ok & linked["area_level"].eq("법정동")] = LEGAL
    return out


def split_totals(linked: pd.DataFrame, values: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """행정동·읍면 합계와 법정동 합계."""
    where = placement(linked)
    admin = linked[where == ADMIN].groupby("area")[values].sum()
    legal = linked[where == LEGAL].groupby("area")[values].sum()
    return admin, legal


def region(linked: pd.DataFrame) -> pd.Series:
    """행이 동 지역인지 읍면인지. 애매함은 후보가 모두 동이면 동. 모르면 None."""

    def one(level, candidates):
        if level in ("행정동", "법정동"):
            return "동"
        if level == "읍면":
            return "읍면"
        levels = {area_level(c, "동") for c in str(candidates or "").split(" / ") if c}
        return levels.pop() if len(levels) == 1 else None

    candidates = (
        linked["candidates"] if "candidates" in linked else pd.Series(None, index=linked.index)
    )
    return pd.Series(
        [one(lv, c) for lv, c in zip(linked["area_level"], candidates)], index=linked.index
    )


def coverage(linked: pd.DataFrame, value: str | None, indicator: str, unit: str) -> pd.DataFrame:
    """지표별 반영 현황. value가 None이면 개수. 동 지역 자료 중 행정동 표에 들어간 비율도 낸다."""
    where = placement(linked)
    amounts = linked[value] if value else pd.Series(1, index=linked.index)
    totals = amounts.groupby(where).sum().reindex(PLACEMENTS, fill_value=0)
    dong = region(linked).eq("동") & where.ne(EXCLUDED)
    dong_total = amounts[dong].sum()
    dong_placed = amounts[dong & where.eq(ADMIN)].sum()
    row = {
        "지표": indicator,
        "단위": unit,
        "전체": amounts.sum(),
        **totals.to_dict(),
        "동 지역 행정동 반영 (%)": dong_placed / dong_total * 100 if dong_total else None,
    }
    return pd.DataFrame([row])


def bus_indicator(period: AnalysisPeriod, months: int, stations: pd.DataFrame):
    bus = load_bus_usage(start=period.start_date, end=period.end_date)
    totals = (
        bus.data.groupby("station_key", as_index=False)["user_count"]
        .sum()
        .rename(columns={"user_count": "users"})
    )
    if totals["users"].sum() != bus.data["user_count"].sum():
        raise ValueError("정류소별 합계가 원자료 합계와 다릅니다")
    linked = mark_exclusions(link_bus_usage(totals, stations))
    admin, _ = split_totals(linked, ["users"])
    admin = (admin["users"] / months).rename("버스 이용자 (월평균)")
    notes = [f"버스 이상일 {len(bus.excluded_dates)}일 제외 (같은 달 같은 요일 중앙값의 20% 미만)"]
    return admin, coverage(linked, "users", "버스 이용자", "명 (기간 합계)"), notes


def wifi_indicators(period: AnalysisPeriod, months: int, ap, stations, boundaries):
    users = period.filter_months(load_wifi_users())
    user_totals = (
        users.groupby("wifi_place_name", as_index=False)["user_count"]
        .sum()
        .rename(columns={"user_count": "users"})
    )
    linked_users = mark_exclusions(link_wifi_places(user_totals, ap, stations, boundaries))

    usage = period.filter_months(pd.read_parquet(WIFI_USAGE_AGG_PATH))
    usage = usage[usage["visit_type"].notna()]
    amount = usage.pivot_table(
        index="wifi_place_name", columns="visit_type", values="use_amount", aggfunc="sum"
    ).fillna(0)
    usage_totals = pd.DataFrame(
        {
            "wifi_place_name": amount.index,
            "users": amount.sum(axis=1).to_numpy(),
            "tourism": amount.get(TOURISM_VISIT_TYPE, pd.Series(0, index=amount.index)).to_numpy(),
        }
    ).reset_index(drop=True)
    linked_usage = mark_exclusions(link_wifi_places(usage_totals, ap, stations, boundaries))

    admin_u, legal_u = split_totals(linked_users, ["users"])
    admin_a, legal_a = split_totals(linked_usage, ["users", "tourism"])

    def frame(u, a):
        return pd.DataFrame(
            {
                "와이파이 사용자 (월평균)": u["users"] / months,
                "와이파이 관광 사용량 비중 (%)": a["tourism"] / a["users"] * 100,
            }
        )

    cov = pd.concat(
        [
            coverage(linked_users, "users", "와이파이 사용자", "명 (월별 합계)"),
            coverage(linked_usage, "users", "와이파이 사용량", "사용량 (방문유형 있는 것)"),
        ]
    )
    return frame(admin_u, admin_a), frame(legal_u, legal_a), cov


def lodging_frame(path: Path = LODGING_PATH) -> pd.DataFrame:
    """영업 중인 관광숙박업. 지번 주소의 동은 법정동."""
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    df = df[df["openStatus"].eq(OPEN_STATUS)].copy()
    df["area"] = df["addressJibun"].map(parse_area)
    df["area_level"] = df["area"].map(lambda a: area_level(a, "법정동"))
    df["status"] = df["area"].notna().map({True: LINKED, False: NOT_FOUND})
    df["rooms"] = pd.to_numeric(df["roomCount"])
    df["places"] = 1
    df["rooms_missing"] = df["rooms"].isna().astype(int)
    return df.reset_index(drop=True)


def converted_rooms(df: pd.DataFrame, mapping: pd.DataFrame) -> float:
    """변환표로 행정동 하나로 바뀐 숙박업 객실 수."""
    return df.loc[df["conversion"].eq("1:1 변환"), "rooms"].sum()


def lodging_indicator(mapping: pd.DataFrame):
    raw = lodging_frame()
    df = convert_legal_to_admin(raw, mapping)
    admin, legal = split_totals(df, ["rooms", "places", "rooms_missing"])

    def frame(t):
        return pd.DataFrame(
            {
                "관광숙박업 객실 수": t["rooms"],
                "관광숙박업 수": t["places"],
                "객실 수 미확인 업소": t["rooms_missing"],
            }
        )

    cov = pd.concat(
        [
            coverage(df, None, "관광숙박업 (영업 중)", "곳"),
            coverage(df, "rooms", "관광숙박업 객실", "실 (객실 수 있는 곳)"),
        ]
    )
    # 오류 의심 짝을 빼지 않았을 때(A안)와 비교
    strict = convert_legal_to_admin(raw, mapping.drop(columns="used"))
    legal_rooms = raw.loc[raw["area_level"].eq("법정동"), "rooms"].sum()
    rooms_a, rooms_b = converted_rooms(strict, mapping), converted_rooms(df, mapping)
    by_reason = (
        df[df["area_level"].ne("읍면")]
        .groupby(df["conversion"].fillna("-"))["rooms"]
        .agg(["size", "sum"])
    )
    compare_note = (
        f"숙박업 동 지역 객실 {legal_rooms:,.0f}실 중 행정동으로 변환: "
        f"오류 의심 짝 포함(A안) {rooms_a:,.0f}실, 오류 의심 짝 제외(B안) {rooms_b:,.0f}실 "
        f"(+{rooms_b - rooms_a:,.0f}실)"
    )
    notes = [
        compare_note,
        "숙박업 변환 결과: "
        + ", ".join(f"{k} {int(r['size'])}곳 {r['sum']:,.0f}실" for k, r in by_reason.iterrows()),
    ]
    return frame(admin), frame(legal), cov, notes


def spot_frame(period: AnalysisPeriod) -> pd.DataFrame:
    """관광지별 월평균 유입자 수 (기간 안에서 자료가 있는 달만)."""
    visitors = period.filter_months(load_tourist_spot_visitors())
    per_spot = visitors.groupby("sight_name")["visitors"].agg(["mean", "size"]).reset_index()
    per_spot.columns = ["sight_name", "monthly", "months"]
    table = load_spot_table()
    usable = load_spot_areas()["sight_name"]
    table["area"] = table["admin_area"].where(table["sight_name"].isin(usable))
    # 동 지역 여부는 주소(법정동·읍면)로 판단
    table["candidates"] = table["area"].fillna(table["admin_area"]).fillna(table["address_area"])
    table["excluded_reason"] = table["method"].eq(METHOD_MULTI).map({True: "여러 동에 걸침"})
    cols = ["sight_name", "area", "candidates", "excluded_reason"]
    df = per_spot.merge(table[cols], on="sight_name", how="left", validate="1:1")
    df["area_level"] = df["area"].map(lambda a: area_level(a, "행정동"))
    df["status"] = df["area"].notna().map({True: LINKED, False: NOT_FOUND})
    df["spots"] = 1
    return df


def spot_indicator(period: AnalysisPeriod):
    df = spot_frame(period)
    admin, legal = split_totals(df, ["monthly", "spots"])

    def frame(t):
        return pd.DataFrame({"관광지 유입자 (월평균)": t["monthly"], "관광지 수": t["spots"]})

    short = df[df["months"] < df["months"].max()]
    confirmed = int(df["status"].eq(LINKED).sum())
    notes = [f"관광지 위치는 tourist_spot_areas.csv에서 '확인'된 {confirmed}곳만 반영"]
    if len(short):
        notes.append(
            "자료가 일부 달만 있는 관광지 (있는 달로만 평균): "
            + ", ".join(f"{r.sight_name} {r.months}개월" for r in short.itertuples())
        )
    return frame(admin), frame(legal), coverage(df, None, "관광지", "곳"), notes


def festival_frame(boundaries) -> pd.DataFrame:
    """2026년 축제 (중복 제외). 위치는 좌표가 들어가는 행정동 경계로 판정."""
    df = load_festivals()
    df = df[~df["is_duplicate"]].copy()
    start = pd.to_datetime(df["축제시작일자"])
    end = pd.to_datetime(df["축제종료일자"])
    df = df[start.dt.year.eq(FESTIVAL_YEAR)].copy()
    df["start_month"] = start.dt.month
    df["long_event"] = ((end - start).dt.days + 1 > LONG_EVENT_DAYS).astype(int)
    df["area"] = [boundaries.locate(lat, lon) for lat, lon in zip(df["위도"], df["경도"])]
    df["area_level"] = df["area"].map(lambda a: area_level(a, "행정동"))
    df["status"] = df["area"].notna().map({True: LINKED, False: NOT_FOUND})
    df["excluded_reason"] = df["축제명"].map(
        lambda n: "여러 동에 걸친 축제" if n in MULTI_AREA_FESTIVALS else None
    )
    df["festivals"] = 1
    return df.reset_index(drop=True)


def month_list(months: pd.Series) -> str:
    return "·".join(str(m) for m in sorted(set(months))) + "월"


def festival_indicator(boundaries):
    df = festival_frame(boundaries)
    admin_rows = df[placement(df) == ADMIN]
    admin = admin_rows.groupby("area").agg(
        **{
            "2026 축제 수": ("festivals", "sum"),
            "개최 월 (시작 월)": ("start_month", month_list),
            "장기 행사 수 (30일 초과)": ("long_event", "sum"),
        }
    )
    unplaced = df[placement(df) == UNPLACED]["축제명"].tolist()
    notes = [f"축제 위치 미연결 (좌표 없음 또는 경계 밖): {', '.join(unplaced) or '없음'}"]
    return admin, coverage(df, None, "2026 축제", "건 (중복 제외)"), notes


def build_compare(period: AnalysisPeriod = COMPARISON_PERIOD):
    months = months_in(period)
    boundaries = load_jeju_boundaries()
    ap, stations = load_wifi_ap(), load_bus_stations()
    mapping = build_pair_mapping(collect_pairs(ap, stations, boundaries))
    index = pd.Index(sorted(boundaries.areas), name="area")

    bus, bus_cov, bus_notes = bus_indicator(period, months, stations)
    wifi_admin, wifi_legal, wifi_cov = wifi_indicators(period, months, ap, stations, boundaries)
    lodging_admin, lodging_legal, lodging_cov, lodging_notes = lodging_indicator(mapping)
    spot_admin, spot_legal, spot_cov, spot_notes = spot_indicator(period)
    fest_admin, fest_cov, fest_notes = festival_indicator(boundaries)

    unknown = set(bus.index) - set(index)
    if unknown:
        raise ValueError(f"경계 파일에 없는 행정동: {', '.join(sorted(unknown))}")

    admin = pd.concat([bus, wifi_admin, lodging_admin, spot_admin, fest_admin], axis=1).reindex(
        index
    )
    count_cols = [
        "관광숙박업 객실 수",
        "관광숙박업 수",
        "객실 수 미확인 업소",
        "관광지 유입자 (월평균)",
        "관광지 수",
        "2026 축제 수",
        "장기 행사 수 (30일 초과)",
    ]
    admin[count_cols] = admin[count_cols].fillna(0)
    admin["개최 월 (시작 월)"] = admin["개최 월 (시작 월)"].fillna("-")
    is_dong = admin.index.map(lambda a: area_level(a, "행정동") == "행정동")
    admin.insert(0, "구분", ["동" if d else "읍면" for d in is_dong])

    legal = pd.concat([wifi_legal, lodging_legal, spot_legal], axis=1).sort_index()
    legal.index.name = "area"

    cov = pd.concat([bus_cov, wifi_cov, lodging_cov, spot_cov, fest_cov], ignore_index=True)
    notes = [
        f"분석 기간 {period.label()} ({months}개월). 숙박업은 수집 시점 현황, 축제는 2026년 일정",
        *bus_notes,
        "와이파이 관광 비중 = 방문유형 '관광' 사용량 ÷ 방문유형이 있는 사용량",
        "동 지역 와이파이는 AP 좌표가 들어가는 행정동으로 판정 (그룹의 AP가 여러 행정동이면 애매함)",
        *lodging_notes,
        *spot_notes,
        *fest_notes,
        "축제 위치는 좌표가 들어가는 행정동 경계로 판정 (경계: vuski/admdongkor ver20261001)",
    ]
    return admin.reset_index(), legal.reset_index(), cov, notes, mapping


def dong_fill(admin: pd.DataFrame) -> pd.DataFrame:
    """지표별로 동 지역 행 중 값이 있는(0보다 큰) 곳 수."""
    dong = admin[admin["구분"] == "동"]
    cols = [c for c in admin.columns if c not in ("area", "구분", "개최 월 (시작 월)")]
    filled = {c: int((pd.to_numeric(dong[c], errors="coerce").fillna(0) > 0).sum()) for c in cols}
    return pd.DataFrame(
        {"지표": list(filled), f"값이 있는 동 (전체 {len(dong)}곳)": list(filled.values())}
    )


def _display(df: pd.DataFrame) -> pd.DataFrame:
    """표 출력용: 소수 한 자리, 빈칸은 '-'."""
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].round(1)
    out = out.astype(object)
    return out.where(out.notna(), "-")


def mapping_table(mapping: pd.DataFrame) -> pd.DataFrame:
    out = mapping.assign(
        share=(mapping["share"] * 100).round(1),
        used=mapping["used"].map({True: "근거", False: "제외"}),
    )
    out = out[
        [
            "legal_dong",
            "admin_dong",
            "pairs",
            "places",
            "share",
            "used",
            "suspect_reason",
            "admin_count",
        ]
    ]
    out.columns = [
        "법정동",
        "행정동 (좌표 판정)",
        "짝 수",
        "장소 수",
        "법정동 안 비율 (%)",
        "변환 근거",
        "오류 의심 사유",
        "근거 행정동 수",
    ]
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="후보지 비교표")
    parser.add_argument("--start", help="시작 월 YYYYMM")
    parser.add_argument("--end", help="끝 월 YYYYMM")
    args = parser.parse_args(argv)
    period = analysis_period(args.start, args.end, default=COMPARISON_PERIOD)

    admin, legal, cov, notes, mapping = build_compare(period)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(OUTPUT_DIR / "legal_admin_mapping.csv", index=False, encoding="utf-8-sig")
    admin.to_csv(OUTPUT_DIR / "candidate_compare.csv", index=False, encoding="utf-8-sig")
    legal.to_csv(OUTPUT_DIR / "candidate_compare_legal_dong.csv", index=False, encoding="utf-8-sig")

    print(f"## 후보지 비교표 ({period.label()})")
    print(table(_display(admin.rename(columns={"area": "읍면동"}))))
    print("\n## 행정동으로 바꾸지 못한 법정동 자료")
    print(table(_display(legal.rename(columns={"area": "법정동"}))))
    print("\n## 지표별 반영 현황")
    print(table(_display(cov)))
    print("\n## 동 지역 칸 채움")
    print(table(dong_fill(admin)))
    counts = mapping.groupby("legal_dong")["admin_count"].first()
    print(
        f"\n## 법정동 → 행정동 변환표 (법정동 {len(counts)}개: 1:1 {int((counts == 1).sum())}, "
        f"애매함 {int((counts > 1).sum())}, 근거 부족 {int((counts == 0).sum())})"
    )
    print(table(_display(mapping_table(mapping))))
    print("\n## 주의")
    print("\n".join(f"- {n}" for n in notes))


if __name__ == "__main__":
    main()
