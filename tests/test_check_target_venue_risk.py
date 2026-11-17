from pathlib import Path

import pandas as pd
import pytest

from agent.demo_cards import DEMO_REQUEST, demo_proposal
from agent.draft_contracts import CheckResult
from agent.fake_checks import FAKE_TOOLS
from agent.verify import run_checks
from analytics import reference_data
from analytics.bus_hourly import StationHourly
from analytics.check_risk import check_risk, night_residents
from analytics.check_target import ELDERLY_WARNING, check_target, parse_target
from analytics.check_timing import TimingData, week_month
from analytics.check_venue import check_venue, event_hour_usage, night_return_usage
from analytics.flow_source import FlowData
from analytics.real_checks import REAL_TOOLS

REGION = "제주시 애월읍"
OTHER = "제주시 한림읍"
CARD = demo_proposal().ideas[0]


def card(months=(5,), material="감귤", venue=None):
    return CARD.model_copy(
        update={
            "material": material,
            "timing": CARD.timing.model_copy(update={"recommended_months": list(months)}),
            "venue": venue or [],
        }
    )


def request(region=REGION, target="가족"):
    return DEMO_REQUEST.model_copy(update={"region": region, "target": target})


# ---------- check_target ----------


@pytest.mark.parametrize(
    ("text", "ages", "sex"),
    [
        ("가족", {"10대 미만", "30대", "40대"}, None),
        ("20~30대 여성", {"20대", "30대"}, "여성"),
        ("청년", {"20대", "30대"}, None),
        ("중장년", {"40대", "50대"}, None),
        ("어르신", {"60대 이상"}, None),
        ("엄마와 아이", {"10대 미만", "30대", "40대"}, "여성"),
        ("40대", {"40대"}, None),
        ("10대 미만 자녀", {"10대 미만", "30대", "40대"}, None),
        ("관광객", set(), None),
    ],
)
def test_parse_target(text, ages, sex):
    got_ages, got_sex, _ = parse_target(text)
    assert (got_ages, got_sex) == (ages, sex)


def demographics(dong_family: float, months=range(1, 13), may_family=None) -> pd.DataFrame:
    """동네 2곳. 애월읍 가족(30대) 비중을 바꾼다. 한림읍은 30대 30%, 20대 70%."""
    rows = []
    for m in months:
        fam = may_family if (may_family is not None and m == 7) else dong_family
        for area, share in [(REGION, fam), (OTHER, 0.3)]:
            rows += [
                (area, m, "여성", "30대", int(1000 * share)),
                (area, m, "남성", "20대", int(1000 * (1 - share))),
            ]
    df = pd.DataFrame(rows, columns=["admin_area", "month", "sex", "age_range", "users"])
    return df.assign(source="와이파이 장소별 사용자 현황 (성·연령) 테스트")


def target(dong_family, req=None, c=None, **kw):
    return check_target(
        c or card(), req or request(), demographics(dong_family, **kw), use_flow=False
    )


def test_target_levels_and_warning():
    # 제주 평균 = (애월 + 한림) / 2000
    assert target(0.4).status == "pass"  # 0.4 / 0.35 = 1.14
    assert target(0.28).status == "conditional"  # 0.28 / 0.29 = 0.97
    r = target(0.1)  # 0.1 / 0.2 = 0.5: 낮아도 fail이 아니라 conditional (대상은 사용자가 정한 값)
    assert r.status == "conditional" and r.check == "check_target"
    assert ELDERLY_WARNING in r.warnings and not r.is_synthetic
    assert r.evidence["age_share"]["ratio"] == 0.5


def test_low_target_only_warns_without_suggestion():
    """대상 비중이 많이 낮아도 Agent가 고칠 수 없으니 경고만 (QA #7·#13)."""
    r = target(0.1, may_family=0.6)
    assert r.status == "conditional" and r.suggestion is None
    assert "제주 평균보다 낮아요" in r.reason
    assert (
        "이 동네는 가족 비중이 제주 평균보다 낮아요. 홍보 대상을 넓히거나 장소를 바꿔보세요."
        in r.warnings
    )
    assert any("20대" in w for w in r.warnings)  # 이 동네에서 비중 높은 연령대
    slightly = target(0.28)  # 0.97배: 조금 낮음, 경고 없음
    assert "조금 낮아요" in slightly.reason
    assert not any("홍보 대상을 넓히" in w for w in slightly.warnings)


def test_share_numbers_never_look_contradictory():
    """0.1% vs 0.1%, 0.80배처럼 판정과 어긋나 보이는 표시를 막는다 (QA 2차 #13)."""
    from analytics.check_target import share_numbers

    n = share_numbers(0.00068, 0.001)
    assert n["dong_share_pct"] != n["jeju_share_pct"]  # 0.07% / 0.1%
    assert share_numbers(0.2, 0.4)["dong_share_pct"] == 20.0  # 보통은 소수 첫째 자리
    assert share_numbers(0.8975, 1.0)["ratio"] == 0.897  # 0.90으로 반올림하면 0.9 기준과 어긋남
    assert share_numbers(0.5, 1.0)["ratio"] == 0.5


def test_target_checks_sex_too():
    r = target(0.4, req=request(target="가족 여성"))
    assert r.evidence["sex_share"] is not None and r.evidence["sex"] == "여성"


def test_target_low_data_notice():
    small = demographics(0.4)
    small = pd.concat([small, small.assign(admin_area="제주시 연동", users=small["users"] * 100),
                       small.assign(admin_area="제주시 노형동", users=small["users"] * 100)])  # fmt: skip
    small.loc[small["admin_area"] == REGION, "users"] //= 100  # 애월읍만 아주 적게
    r = check_target(card(), request(), small, use_flow=False)
    assert any("동네 중앙값" in n for n in r.evidence["low_data"])
    assert any("대상 연령대 사용자가" in n for n in r.evidence["low_data"])
    assert any("자료가 적어 결과가 불안정" in w for w in r.warnings)
    assert target(0.4).evidence["low_data"] == []


def test_target_pending_cases():
    assert target(0.4, req=request(target=None)).status == "pending"
    assert target(0.4, req=request(target="관광객")).status == "pending"
    assert target(0.4, req=request(region=None)).status == "pending"
    assert target(0.4, req=request(region="제주시 없는동")).status == "pending"


def flow_frame() -> pd.DataFrame:
    """4-11 형식: 애월읍 야간 거주인구 많음, 한림읍 적음."""
    rows = []
    for area, resd in [(REGION, 300.0), (OTHER, 100.0)]:
        for t in range(1, 25):
            rows.append({"base_date": pd.Timestamp("2025-05-12"), "time": t, "emd_nm": area,
                         "sex": "여성", "age": "3034", "age_band": "30대", "resd": "제주",
                         "resd_pop_cnt": resd, "visit_pop_cnt": 10.0})  # fmt: skip
    return pd.DataFrame(rows)


def fake_flow(synthetic=True) -> FlowData:
    return FlowData(flow_frame(), synthetic, Path("flow.csv"), ("2025-05-12", "2025-05-12"))


def test_target_shows_synthetic_flow(monkeypatch):
    import analytics.flow_source as fs

    monkeypatch.setattr(fs, "load_flow", lambda: fake_flow(True))
    r = check_target(card(), request(), demographics(0.4), use_flow=True)
    assert r.evidence["flow"]["is_synthetic"] and r.evidence["flow"]["data_label"] == "가상 데이터"
    assert not r.is_synthetic  # 판정은 와이파이 실데이터
    assert r.status == "pass"  # 판정은 와이파이로


# ---------- check_venue ----------


def venue_tables(near_stop=True, busy=True, region_places=True):
    places = pd.DataFrame(
        {
            "wifi_place_name": ["애월해안공원", "애월작은카페", "한림공원"],
            "admin_area": [REGION, REGION, OTHER],
            "latitude": [33.46, 33.47, 33.39],
            "longitude": [126.31, 126.32, 126.24],
            "tourism_share_pct": [80.0, 40.0, 70.0],
            "small": [False, False, False],
            "source": "와이파이 테스트",
        }
    )
    if not region_places:
        places = places[places["admin_area"] != REGION]
    offset = 0.003 if near_stop else 0.02  # 약 330m / 2.2km
    stations = pd.DataFrame(
        {
            "stationId": ["1", "2", "3"],
            "stationName": ["애월항", "곽지", "한림공원입구"],
            "latitude": [33.46 + offset, 33.0, 33.391],
            "longitude": [126.31, 126.0, 126.24],
            "daily_users": [100.0 if busy else 1.0, 50.0, 80.0],
            "source": "버스 테스트",
        }
    )
    neighbors = pd.DataFrame({"admin_area": [REGION], "neighbor": [OTHER]})
    return places, stations, neighbors


def test_venue_pass_with_candidates():
    r = check_venue(card(), request(), venue_tables(), hourly=None)
    assert r.status == "pass" and r.check == "check_venue"
    top = r.evidence["candidate_places"][0]
    assert top["name"] == "애월해안공원" and top["stop_name"] == "애월항"
    assert 300 < top["stop_distance_m"] < 360 and top["stop_daily_users"] == 100.0
    assert r.evidence["event_hours"]["status"] == "pending"


def test_venue_conditional_needs_shuttle():
    for tables in (venue_tables(near_stop=False), venue_tables(busy=False)):
        r = check_venue(card(), request(), tables)
        assert r.status == "conditional" and "셔틀 필요" in r.reason


def test_venue_radius_is_adjustable():
    r = check_venue(card(), request(), venue_tables(), radius_m=200)
    assert r.status == "conditional"


def test_venue_fail_suggests_neighbor():
    r = check_venue(card(), request(), venue_tables(region_places=False))
    assert r.status == "fail" and r.suggestion.field == "venue"
    assert r.suggestion.value[0]["name"] == "한림공원"
    assert r.suggestion.value[0]["admin_area"] == OTHER


def test_venue_pending_and_no_hourly_data():
    assert check_venue(card(), request(region=None), venue_tables()).status == "pending"
    assert check_venue(card(), request(), (None, None, None)).status == "pending"
    assert event_hour_usage(["1"], [18, 19], data=None) is None
    assert night_return_usage(["1"], data=None) is None


def station_hourly(night=0) -> StationHourly:
    """정류소 1(애월항) 하루: 낮 12시 승차 30명, 밤 22시 승차 night명, 하차는 셈에서 뺌."""
    rows = []
    for day in ("20250512", "20250513"):
        rows += [(day, "1", "승차", 12, 30), (day, "1", "하차", 12, 99)]
        if night:
            rows.append((day, "1", "승차", 22, night))
    df = pd.DataFrame(
        rows, columns=["base_date", "bus_station_id", "get_on_off_type", "hour", "user_count"]
    )
    return StationHourly(df, True, Path("demo.csv"))


def test_venue_hourly_evidence_is_labeled_but_not_judged():
    r = check_venue(card(), request(), venue_tables(), hourly=station_hourly(night=0))
    ev, night = r.evidence["event_hours"], r.evidence["night_return"]
    assert ev["stops"][0]["daily_boarding"] == 30.0 and ev["data_label"] == "가상 데이터"
    assert night["stops"][0]["daily_boarding"] == 0
    assert any("야간 귀가" in w and "셔틀" in w for w in r.warnings)
    assert r.status == "pass" and not r.is_synthetic  # 판정은 일별 이용(실데이터)
    r = check_venue(card(), request(), venue_tables(), hourly=station_hourly(night=5))
    assert r.evidence["night_return"]["stops"][0]["daily_boarding"] == 5.0
    assert not any("셔틀을 검토" in w for w in r.warnings)


def test_night_share_warning_from_hub():
    from analytics.bus_hourly import band_shares, night_share_warning

    hub = pd.DataFrame(
        {
            "base_date": ["20250512"] * 2,
            "day_of_week": ["월"] * 2,
            "base_hour": ["13시-15시", "22시-24시"],
            "user_type": ["일반"] * 2,
            "user_count": [95, 5],
        }
    )
    assert "하루의 5.0%" in night_share_warning(band_shares(hub))


# ---------- check_risk ----------


def timing_data(festivals: pd.DataFrame) -> TimingData:
    return TimingData(
        weekly=None, monthly=None, station_by_dong=None, outsider=None,
        festivals=festivals, keywords=pd.DataFrame({"material": ["감귤"], "keywords": ["감귤"]}),
    )  # fmt: skip


def may_weeks():
    return [w for w in range(1, 53) if week_month(w) == 5]


def timing_result(same=None) -> CheckResult:
    return CheckResult(
        check="check_timing",
        status="pass",
        reason="r",
        evidence={"overlapping_festivals": same or [], "recommended_week_numbers": may_weeks()},
    )


def festivals(*rows):
    cols = ["name", "start", "end", "months", "source", "dates_known", "admin_area"]
    return pd.DataFrame(list(rows), columns=cols)


def risk(c=None, req=None, fests=None, same=None, flow=None, areas=(REGION,)):
    return check_risk(
        c or card(), req or request(), venue_areas=list(areas) if areas else None,
        timing_result=timing_result(same), timing_data=timing_data(fests if fests is not None else festivals()),
        flow=flow,
    )  # fmt: skip


def test_risk_pass_and_congestion_pending():
    r = risk()
    assert r.status == "pass" and r.check == "check_risk"
    assert r.evidence["congestion"]["status"] == "pending"
    assert any("교통량" in w for w in r.warnings)


def test_risk_reuses_same_material_festivals():
    same = [{"name": "감귤 축제", "month": 5}]
    r = risk(same=same)
    assert r.status == "conditional" and "감귤 축제" in r.reason


def test_risk_warns_other_festival_same_area_same_week():
    s, e = pd.Timestamp("2026-05-14"), pd.Timestamp("2026-05-15")
    fests = festivals(
        ("애월 음악회", s, e, "5", "문체부 2026 계획", True, REGION),
        ("한림 음악회", s, e, "5", "문체부 2026 계획", True, OTHER),  # 다른 동네
        ("애월 감귤 장터", s, e, "5", "문체부 2026 계획", True, REGION),  # 같은 재료
        ("애월 봄 행사", pd.NaT, pd.NaT, "5", "문체부 2026 계획", False, REGION),
    )
    r = risk(fests=fests)
    names = [f["name"] for f in r.evidence["same_area_other_festivals"]]
    assert names == ["애월 음악회", "애월 봄 행사"]
    assert any("애월 음악회" in w and "겹쳐요" in w for w in r.warnings)
    assert any("날짜 미확인" in w for w in r.warnings)
    assert r.status == "pass"  # 다른 재료 축제는 경고만


def test_risk_residential_density_with_synthetic_flag():
    r = risk(flow=fake_flow(True))
    assert r.status == "conditional" and "소음 민원 주의" in r.reason
    assert r.is_synthetic and any("가상 데이터" in w for w in r.warnings)
    assert r.evidence["residential"]["areas"][0]["ratio"] == 1.5
    r = risk(flow=fake_flow(False), areas=(OTHER,))
    assert r.status == "pass" and not r.is_synthetic


def test_risk_uses_venue_from_card():
    from agent.draft_contracts import VenueCandidate

    c = card(venue=[VenueCandidate(name="한림공원", admin_area=OTHER)])
    r = check_risk(c, request(), timing_result=timing_result(), timing_data=timing_data(festivals()),
                   flow=fake_flow(False))  # fmt: skip
    assert r.evidence["venue_areas"] == [OTHER] and r.status == "pass"


def test_risk_reports_congestion_when_roads_are_much_slower():
    """정체 기준 80%는 그대로, 행사 시간대에 평소보다 많이 느린 구간이 있으면 "정체 주의"."""
    from analytics.traffic_source import TrafficData

    links = pd.DataFrame(
        {"link_id": ["L1"], "road_name": ["애월해안로"], "mid_lat": [33.46], "mid_lon": [126.31]}
    )
    hourly = pd.DataFrame(
        [("L1", weekend, h, 20.0 if weekend and 11 <= h <= 19 else 50.0)
         for weekend in (False, True) for h in range(24)],
        columns=["link_id", "weekend", "hour", "average_speed"],
    )  # fmt: skip
    c = card(venue=[])
    venue = CheckResult(check="check_venue", status="pass", reason="r", evidence={
        "candidate_places": [{"name": "애월해안공원", "admin_area": REGION, "latitude": 33.46, "longitude": 126.31}]})  # fmt: skip
    from analytics import check_risk as cr

    r = cr.check_risk(c, request(), timing_result=timing_result(), timing_data=timing_data(festivals()),
                      flow=None, traffic=TrafficData(links, hourly, True), venue_result=venue)  # fmt: skip
    assert r.status == "conditional" and "정체 주의" in r.reason
    assert r.evidence["congestion"]["slow_links"][0]["road_name"] == "애월해안로"
    assert r.is_synthetic


def test_night_residents_averages_evening_hours():
    night = night_residents(flow_frame())
    assert night[REGION] == 300.0 and night[OTHER] == 100.0


# ---------- 연결 ----------


def test_real_tools_cover_all_five_checks():
    assert set(REAL_TOOLS) == set(FAKE_TOOLS)
    results = run_checks(card(), request(region=None, target=None), {**FAKE_TOOLS, **REAL_TOOLS})
    assert [r.check for r in results] == list(FAKE_TOOLS)


def test_reference_first(tmp_path, monkeypatch):
    monkeypatch.setattr(reference_data, "REFERENCE_DIR", tmp_path / "ref")
    monkeypatch.setattr(reference_data, "PROCESSED_DIR", tmp_path / "processed")
    assert reference_data.reference_first("a.csv") == tmp_path / "processed" / "a.csv"
    (tmp_path / "ref").mkdir()
    (tmp_path / "ref" / "a.csv").write_text("x")
    assert reference_data.reference_first("a.csv") == tmp_path / "ref" / "a.csv"
