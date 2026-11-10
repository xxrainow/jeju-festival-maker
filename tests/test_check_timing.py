from functools import partial

import pandas as pd
import pytest

from agent.demo_cards import DEMO_REQUEST, demo_proposal
from agent.fake_checks import FAKE_TOOLS
from agent.fake_checks import check_timing as fake_check_timing
from agent.verify import verify_idea
from analytics.check_timing import (
    REAL_TOOLS,
    TimingData,
    check_timing,
    festival_dates,
    mark_bad_weeks,
    weather_fail_table,
    week_month,
)
from analytics.outsider_index import (
    WIFI_SOURCE,
    choose_index,
    flow_outsider_index,
    wifi_outsider_index,
)
from analytics.weather import RISKS

REGION = "제주시 애월읍"
CARD = demo_proposal().ideas[0]
KEYWORDS = pd.DataFrame({"material": ["감귤"], "keywords": ["감귤|한라봉"]})


def weeks_of(month: int) -> list[int]:
    return [w for w in range(1, 53) if week_month(w) == month]


def weekly_table(bad: dict[int, tuple[float, int]] | None = None) -> pd.DataFrame:
    """제주 지점 53주. bad: {주: (폭우 배수, 9년 중 발생 연수)}."""
    rows = []
    for week in range(1, 54):
        ratio, years = (bad or {}).get(week, (1.0, 1))
        rows.append(
            {
                "station": "제주",
                "week": week,
                "heavy_rain_ratio": ratio,
                "heavy_rain_years": years,
                "strong_wind_ratio": 0.5,
                "strong_wind_years": 1,
            }
        )
    return pd.DataFrame(rows)


def monthly_table() -> pd.DataFrame:
    rows = []
    for month in range(1, 13):
        row = {"station": "제주", "month": month, "worse_than_usual": float("nan")}
        for k in RISKS:
            row |= {f"{k}_days": 0.5, f"{k}_judged_days": 279, f"{k}_ratio": 1.0}
        row |= {"heavy_rain_years": 1, "strong_wind_years": 1, "heat_years": 0}
        row |= {"wind_missing_days": 0, "temp_max_missing_days": 0}
        rows.append(row)
    return pd.DataFrame(rows)


def outsider_table(index: dict[int, float] | None = None) -> pd.DataFrame:
    values = {m: 1.1 for m in range(1, 13)} | (index or {})
    return pd.DataFrame(
        {
            "admin_area": REGION,
            "month": list(values),
            "index": list(values.values()),
            "value": 1.0,
            "places": 10,
            "source": f"{WIFI_SOURCE} 2023-01 ~ 2024-12",
            "is_synthetic": False,
        }
    )


def festival_table(*rows) -> pd.DataFrame:
    """rows: (이름, 시작, 끝) 시작이 None이면 날짜 미확인, 이때 끝 자리에 월."""
    out = []
    for name, start, end in rows:
        if start is None:
            out.append((name, pd.NaT, pd.NaT, str(end), "문체부 2026 계획", False))
        else:
            s, e = pd.Timestamp(start), pd.Timestamp(end)
            months = "|".join(str(m) for m in sorted(set(pd.date_range(s, e).month)))
            out.append((name, s, e, months, "문체부 2026 계획", True))
    cols = ["name", "start", "end", "months", "source", "dates_known"]
    return pd.DataFrame(out, columns=cols)


def data(weekly=None, outsider=None, festivals=None, season=None) -> TimingData:
    return TimingData(
        weekly=mark_bad_weeks(weekly if weekly is not None else weekly_table()),
        monthly=monthly_table(),
        station_by_dong=pd.DataFrame({"admin_area": [REGION], "station": ["제주"]}),
        outsider=outsider if outsider is not None else outsider_table(),
        festivals=festivals if festivals is not None else festival_table(),
        keywords=KEYWORDS,
        material_months={"감귤": season} if season else {},
    )


def card(months: list[int]):
    return CARD.model_copy(
        update={"timing": CARD.timing.model_copy(update={"recommended_months": months})}
    )


def request(region=REGION):
    return DEMO_REQUEST.model_copy(update={"region": region})


def test_pass_keeps_fake_format_and_recommends_weeks():
    r = check_timing(card([5]), request(), data())
    fake = fake_check_timing(card([5]), request())
    assert r.check == fake.check == "check_timing"
    assert set(fake.evidence) <= set(r.evidence)  # 가짜 함수의 칸을 모두 가짐
    assert r.status == "pass" and r.suggestion is None and not r.is_synthetic
    assert r.evidence["outsider_visitors_index"] == {5: 1.1}
    assert r.evidence["low_months"] == []
    assert len(r.evidence["recommended_weeks"]) == len(weeks_of(5))
    assert r.evidence["recommended_weeks"][0].startswith("5월")
    assert any(s.startswith(WIFI_SOURCE) for s in r.sources)
    assert any("와이파이 관광 사용량으로 대신" in w for w in r.warnings)


def test_bad_week_needs_ratio_and_years():
    may = weeks_of(5)
    # 일부 주만 나쁘면 pass, 나쁜 주는 추천에서 빠짐
    r = check_timing(card([5]), request(), data(weekly_table({may[0]: (1.6, 2)})))
    assert r.status == "pass" and len(r.evidence["recommended_weeks"]) == len(may) - 1
    # 모든 주가 1.5배 이상 + 2년 이상이면 fail
    all_bad = weekly_table({w: (1.6, 2) for w in may})
    r = check_timing(card([5]), request(), data(all_bad))
    assert r.status == "fail" and r.evidence["bad_weather_months"] == [5]
    assert "폭우·바람" in r.reason
    # 9년 중 1년뿐이거나 1.5배 미만이면 나쁜 주가 아님
    for ratio, years in [(3.0, 1), (1.4, 5)]:
        weekly = weekly_table({w: (ratio, years) for w in may})
        assert check_timing(card([5]), request(), data(weekly)).status == "pass"


def test_rain_and_heat_are_reference_only():
    d = data()
    d.monthly.loc[d.monthly["month"] == 8, ["rainy_ratio", "heat_ratio"]] = 2.0
    r = check_timing(card([8]), request(), d)
    assert r.status == "pass"
    assert any("8월은 평소보다 비·더위가 많아요 (판정에는 쓰지 않음)" in w for w in r.warnings)


def test_fail_drops_only_failing_month():
    r = check_timing(card([5, 12]), request(), data(outsider=outsider_table({12: 0.8})))
    assert r.status == "fail" and r.evidence["low_months"] == [12]
    assert r.suggestion.field == "timing.recommended_months"
    assert r.suggestion.value == [5] and "빼요" in r.suggestion.why
    assert "12월은 외지인 방문 지수(0.80)가 연평균(1)보다 낮아요" in r.reason


def test_all_fail_moves_to_best_passing_month_in_season():
    index = {12: 0.8, 11: 1.2, 1: 1.5, 7: 2.0}
    jan_bad = weekly_table({w: (2.0, 3) for w in weeks_of(1)})
    r = check_timing(
        card([12]), request(), data(jan_bad, outsider_table(index), season=[11, 12, 1])
    )
    # 7월이 지수가 가장 높지만 감귤 제철이 아니고, 1월은 날씨 fail → 11월
    assert r.status == "fail" and r.suggestion.value == [11]
    assert "제철" in r.suggestion.why
    # 제철 안에 통과하는 달이 없으면 제안 없음
    r = check_timing(card([12]), request(), data(outsider=outsider_table(index), season=[12]))
    assert r.suggestion is None and any("통과하는 다른 달이 없어" in w for w in r.warnings)


def test_same_material_festival_is_conditional():
    may = weeks_of(5)
    fests = festival_table(
        ("제5회 한라봉 축제", "2026-05-14", "2026-05-15"),
        ("유채꽃 축제", "2026-05-01", "2026-05-31"),  # 다른 재료
    )
    r = check_timing(card([5]), request(), data(festivals=fests))
    assert r.status == "conditional" and r.suggestion is None
    assert [f["name"] for f in r.evidence["overlapping_festivals"]] == ["제5회 한라봉 축제"]
    assert len(r.evidence["recommended_weeks"]) == len(may) - 1  # 축제 주는 뺌
    assert not any("5/14" in w and "5/15" in w for w in r.evidence["recommended_weeks"])


def test_unavoidable_or_unknown_festival_stays_conditional_with_warning():
    whole = festival_table(("감귤 한 달 축제", "2026-04-20", "2026-06-10"))
    r = check_timing(card([5]), request(), data(festivals=whole))
    assert r.status == "conditional"
    assert any("날짜를 피할 수 없으니" in w for w in r.warnings)
    unknown = festival_table(("감귤 축제", None, 5))
    r = check_timing(card([5]), request(), data(festivals=unknown))
    assert r.status == "conditional"
    assert any("날짜 미확인: 감귤 축제" in w for w in r.warnings)


def test_year_crossing_festival_overlaps_january():
    fests = festival_table(("감귤 새해 축제", "2025-12-29", "2026-01-03"))
    r = check_timing(card([1]), request(), data(festivals=fests))
    assert r.status == "conditional"
    assert len(r.evidence["recommended_weeks"]) == len(weeks_of(1)) - 1


def test_pending_without_region_or_wifi():
    assert check_timing(card([5]), request(None), data()).status == "pending"
    r = check_timing(card([5]), request("제주시 한림읍"), data())
    assert r.status == "pending" and "와이파이" in r.reason


def test_swaps_into_verify_loop():
    tools = {**FAKE_TOOLS, **REAL_TOOLS}
    assert tools["check_timing"] is check_timing
    tools["check_timing"] = partial(check_timing, data=data(outsider=outsider_table({12: 0.8})))
    run = verify_idea(card([5, 12]), request(), tools)
    assert run.final.timing.recommended_months == [5]
    assert run.rounds[-1].results[0].status == "pass"


def test_weather_fail_table_counts_all_bad_months():
    weekly = weekly_table({w: (1.8, 2) for w in weeks_of(8)})
    assert weather_fail_table(weekly, 1.5)["all_bad"].sum() == 1
    assert weather_fail_table(weekly, 2.0)["all_bad"].sum() == 0


def test_festival_dates_prefers_rows_with_dates():
    plan = pd.DataFrame(
        {
            "name": ["제3회 감귤축제", "방어축제"],
            "start_date": [None, None],
            "end_date": [None, None],
            "start_month": [11, 11],
        }
    )
    standard = pd.DataFrame(
        {
            "축제명": ["감귤 축제"],
            "축제시작일자": ["2026-11-20"],
            "축제종료일자": ["2026-12-02"],
            "is_duplicate": [False],
        }
    )
    out = festival_dates(plan, standard).set_index("name")
    assert len(out) == 2
    assert out.loc["감귤 축제", "months"] == "11|12" and out.loc["감귤 축제", "dates_known"]
    assert out.loc["방어축제", "months"] == "11" and not out.loc["방어축제", "dates_known"]


def test_wifi_outsider_index_averages_same_months():
    rows = []
    for year in ("2023", "2024"):
        for m in range(1, 13):
            amount = 300 if m == 8 else 100
            rows.append(("A장소", f"{year}{m:02d}", "관광", amount))
            rows.append(("A장소", f"{year}{m:02d}", "거주", 999))  # 관광만 씀
    usage = pd.DataFrame(
        rows, columns=["wifi_place_name", "base_year_month", "visit_type", "use_amount"]
    )
    areas = pd.DataFrame({"wifi_place_name": ["A장소", "없는장소"], "admin_area": [REGION] * 2})
    out = wifi_outsider_index(usage, areas).set_index("month")
    assert out.loc[8, "index"] == pytest.approx(300 / (1400 / 12))
    assert out["source"].iloc[0].startswith(WIFI_SOURCE) and not out["is_synthetic"].any()


def flow_rows(months: int) -> pd.DataFrame:
    dates = pd.date_range("2025-05-01", periods=months, freq="MS")
    rows = []
    for d in dates:
        for resd, pop in [("그외", 20.0 if d.month == 8 else 10.0), ("제주", 500.0)]:
            rows.append({"base_date": d, "emd_nm": REGION, "resd": resd, "visit_pop_cnt": pop})
    return pd.DataFrame(rows)


def test_flow_index_needs_twelve_months_and_takes_priority():
    assert flow_outsider_index(flow_rows(2), is_synthetic=True) is None
    flow = flow_outsider_index(flow_rows(12), is_synthetic=False).set_index("month")
    assert flow.loc[8, "index"] == pytest.approx(20 / (130 / 12))
    assert flow["source"].iloc[0].startswith("4-11")
    wifi = outsider_table()
    other = wifi.assign(admin_area="제주시 한림읍")
    chosen = choose_index(flow.reset_index(), pd.concat([wifi, other]))
    assert chosen.groupby("admin_area")["source"].first().str[:4].to_dict() == {
        REGION: "4-11",
        "제주시 한림읍": WIFI_SOURCE[:4],
    }
