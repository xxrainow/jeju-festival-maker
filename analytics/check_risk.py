"""위험 확인 도구 check_risk의 실제 버전 (agent/fake_checks.py check_risk와 같은 입출력).

기준 (설계 문서 9-3): 같은 재료 축제 충돌, 주거 밀집(소음 민원), 정체.

1. 축제 충돌
   - 같은 재료·같은 달 제주 축제: check_timing의 목록(overlapping_festivals)을 그대로 쓴다 → conditional
   - 같은 동네 다른 재료 축제가 추천 주와 겹치면 경고 (날짜 미확인이면 같은 달일 때 확인 경고)
2. 주거 밀집: 후보 장소 동네의 야간(19~23시) 거주인구(4-11 resd_pop_cnt)가 제주 동네 평균보다 많으면
   conditional ("소음 민원 주의"). 4-11이 가짜 데이터면 is_synthetic=True + 경고
3. 정체: 후보 장소 반경 1km 안 도로 구간의 주말 11~19시 평균 속도가 평소의 80% 미만이면 conditional ("정체 주의").
   3-10·3-07·3-08 실데이터가 없으면 가상 데이터(data/demo/)로 계산하고 is_synthetic=True

후보 장소 동네: venue_areas 인자 → 카드 venue의 admin_area → check_venue가 고른 후보 → request.region 순.
결과: 하나라도 conditional이면 conditional, 아니면 pass. 계산한 항목이 하나도 없으면 pending.
"""

import pandas as pd

from agent.draft_contracts import CheckResult, IdeaCard, UserRequest
from analytics.check_timing import (
    FESTIVAL_SOURCE,
    _festival_overlaps_week,
    check_timing,
    load_timing_data,
    material_pattern,
    week_text,
)

NIGHT_HOURS = (19, 20, 21, 22, 23)
NOISE = "소음 민원 주의"
CONGESTION = "정체 주의"
EVENT_HOURS = tuple(range(11, 20))  # 주말 11~19시를 행사 시간대로 본다
CONGESTION_RADIUS_M = 1000
SLOW_RATIO = 0.8  # 행사 시간대 속도가 평소의 80% 미만이면 정체


def venue_areas_for(card: IdeaCard, request: UserRequest, venue_result=None) -> list[str]:
    if card.venue:
        return list(dict.fromkeys(v.admin_area for v in card.venue))
    if venue_result is not None:
        cands = venue_result.evidence.get("candidate_places") or []
        areas = [c["admin_area"] for c in cands]
        if areas:
            return list(dict.fromkeys(areas))
    return [request.region] if request.region else []


def night_residents(flow: pd.DataFrame) -> pd.Series:
    """동네별 야간(19~23시) 거주인구: 날짜·시간마다 합친 뒤 평균."""
    f = flow[flow["time"].isin(NIGHT_HOURS)]
    per_hour = f.groupby(["emd_nm", "base_date", "time"])["resd_pop_cnt"].sum()
    return per_hour.groupby("emd_nm").mean()


def residential_check(areas: list[str], flow_data) -> dict | None:
    if flow_data is None or not areas:
        return None
    night = night_residents(flow_data.data)
    avg = float(night.mean())
    rows = []
    for a in areas:
        if a in night:
            rows.append({"admin_area": a, "night_residents": round(float(night[a]), 1),
                         "ratio": round(float(night[a]) / avg, 2)})  # fmt: skip
    if not rows:
        return None
    return {
        "areas": rows,
        "jeju_dong_average": round(avg, 1),
        "hours": f"{NIGHT_HOURS[0]}~{NIGHT_HOURS[-1]}시",
        "dense": [r["admin_area"] for r in rows if r["ratio"] > 1],
        "source": flow_data.label,
        "is_synthetic": flow_data.is_synthetic,
    }


def venue_points(card: IdeaCard, venue_result=None) -> list[dict]:
    """후보 장소 좌표: check_venue 후보, 없으면 카드 venue 이름을 장소 표에서 찾는다."""
    if venue_result is not None:
        cands = venue_result.evidence.get("candidate_places") or []
        return [{"name": c["name"], "lat": c["latitude"], "lon": c["longitude"]} for c in cands]
    if card.venue:
        from analytics.check_venue import load_venue_tables

        places = load_venue_tables()[0]
        if places is not None:
            hit = places[places["wifi_place_name"].isin([v.name for v in card.venue])]
            return [{"name": r.wifi_place_name, "lat": r.latitude, "lon": r.longitude}
                    for r in hit.itertuples()]  # fmt: skip
    return []


def congestion_check(
    points: list[dict],
    traffic=...,
    radius_m: int = CONGESTION_RADIUS_M,
    hours: tuple[int, ...] = EVENT_HOURS,
) -> dict | None:
    """후보 장소 반경 안 도로 구간의 주말 행사 시간대 평균 속도 ÷ 그 구간 평소(전체) 평균 속도.

    SLOW_RATIO 미만인 구간이 있으면 "정체 주의". 교통 자료나 좌표가 없으면 None.
    """
    from analytics.check_venue import _distance_m
    from analytics.traffic_source import load_traffic

    data = load_traffic() if traffic is ... else traffic
    if data is None or not points:
        return None
    near = data.links[
        [any(_distance_m(p["lat"], p["lon"], la, lo) <= radius_m for p in points)
         for la, lo in zip(data.links["mid_lat"], data.links["mid_lon"], strict=True)]
    ]  # fmt: skip
    if near.empty:
        return {"status": "pass", "links_checked": 0, "slow_links": [], "radius_m": radius_m,
                "source": data.label, "is_synthetic": data.is_synthetic,
                "note": f"반경 {radius_m}m 안 도로 구간 없음"}  # fmt: skip
    h = data.hourly[data.hourly["link_id"].isin(near["link_id"])]
    usual = h.groupby("link_id")["average_speed"].mean()
    event = h[h["weekend"] & h["hour"].isin(hours)].groupby("link_id")["average_speed"].mean()
    ratio = (event / usual).dropna()
    names = near.set_index("link_id")["road_name"]
    slow = [
        {"link_id": k, "road_name": names[k], "ratio": round(float(v), 2)}
        for k, v in ratio.sort_values().items()
        if v < SLOW_RATIO
    ]
    return {
        "status": "conditional" if slow else "pass",
        "links_checked": len(ratio),
        "slow_links": slow[:5],
        "min_ratio": round(float(ratio.min()), 2) if len(ratio) else None,
        "hours": f"주말 {hours[0]}~{hours[-1]}시",
        "radius_m": radius_m,
        "source": data.label,
        "is_synthetic": data.is_synthetic,
    }


def check_risk(
    card: IdeaCard,
    request: UserRequest,
    venue_areas: list[str] | None = None,
    timing_result: CheckResult | None = None,
    timing_data=None,
    flow=...,
    traffic=...,
) -> CheckResult:
    from analytics.flow_source import load_flow

    data = timing_data or load_timing_data()
    timing = timing_result or check_timing(card, request, data)
    venue_result = None
    if venue_areas is None:
        if not card.venue and request.region:
            from analytics.check_venue import check_venue

            venue_result = check_venue(card, request)
        venue_areas = venue_areas_for(card, request, venue_result)
    flow_data = load_flow() if flow is ... else flow

    evidence: dict = {"venue_areas": venue_areas}
    sources, warnings, flags = [FESTIVAL_SOURCE], [], []

    # 1. 같은 재료·같은 달 (check_timing 목록 재사용)
    same = timing.evidence.get("overlapping_festivals") or []
    evidence["same_material_festivals"] = same
    if same:
        names = ", ".join(dict.fromkeys(f["name"] for f in same))
        flags.append(f"같은 재료 제주 축제({names})가 같은 달에 있어요")

    # 같은 동네 다른 재료 축제가 추천 주와 겹침
    pattern, _ = material_pattern(card.material, data.keywords)
    fests = data.festivals
    months = set(card.timing.recommended_months)
    weeks = timing.evidence.get("recommended_week_numbers") or []
    local = []
    if len(fests) and "admin_area" in fests:
        others = fests[
            fests["admin_area"].isin(venue_areas) & ~fests["name"].str.contains(pattern, regex=True)
        ]
        for _, f in others.iterrows():
            in_month = bool(months & {int(m) for m in str(f["months"]).split("|")})
            if not in_month:
                continue
            if f["dates_known"]:
                hit = [w for w in weeks if _festival_overlaps_week(f, w)]
                if hit:
                    local.append({"name": f["name"], "admin_area": f["admin_area"],
                                  "start": f["start"].date().isoformat(), "end": f["end"].date().isoformat(),
                                  "weeks": [week_text(w) for w in hit]})  # fmt: skip
            else:
                local.append({"name": f["name"], "admin_area": f["admin_area"], "start": None,
                              "end": None, "weeks": []})  # fmt: skip
    evidence["same_area_other_festivals"] = local
    for f in local:
        if f["weeks"]:
            warnings.append(
                f"같은 동네({f['admin_area']}) 다른 축제 '{f['name']}'({f['start']}~{f['end']})가 "
                f"추천 주({', '.join(f['weeks'])})와 겹쳐요. 인파·주차를 함께 확인해 주세요."
            )
        else:
            warnings.append(
                f"같은 동네({f['admin_area']}) 다른 축제 '{f['name']}'가 같은 달에 있어요 (날짜 미확인)."
            )

    # 2. 주거 밀집
    res = residential_check(venue_areas, flow_data)
    evidence["residential"] = res
    is_synthetic = False
    if res is None:
        warnings.append("4-11 거주인구가 없어(또는 그 동네가 없어) 주거 밀집을 확인하지 못했어요.")
    else:
        sources.append(res["source"])
        if res["dense"]:
            flags.append(
                f"{', '.join(res['dense'])} 야간({res['hours']}) 거주인구가 제주 동네 평균보다 많아 {NOISE}"
            )
        if res["is_synthetic"]:
            is_synthetic = True
            warnings.append("주거 밀집은 4-11 가짜 데이터로 계산했어요. 실제 거주인구가 아니에요.")

    # 3. 정체
    points = venue_points(card, venue_result)
    congestion = congestion_check(points, traffic)
    evidence["congestion"] = congestion or {
        "status": "pending",
        "reason": "교통량 데이터나 후보 장소 좌표가 없음",
    }
    if congestion is None:
        warnings.append("정체는 교통량 데이터나 후보 장소 좌표가 없어 확인하지 않았어요.")
    else:
        sources.append(congestion["source"])
        if congestion["status"] == "conditional":
            worst = congestion["slow_links"][0]
            flags.append(
                f"후보 장소 {congestion['radius_m']}m 안 도로가 {congestion['hours']}에 평소 속도의 "
                f"{worst['ratio']:.0%}로 느려져 {CONGESTION}"
            )
        if congestion["is_synthetic"]:
            is_synthetic = True
            warnings.append("정체는 3-10 교통량 가상 데이터로 계산했어요. 실제 교통량이 아니에요.")

    status = "conditional" if flags else "pass"
    if flags:
        reason = ". ".join(flags) + "."
    else:
        checked = (
            ["같은 재료 축제 충돌"]
            + (["주거 밀집"] if res else [])
            + (["정체"] if congestion else [])
        )
        wait = "" if congestion else " (정체는 데이터 대기)"
        reason = f"{', '.join(checked)}에서 문제가 보이지 않아요{wait}."
    return CheckResult(
        check="check_risk",
        status=status,
        reason=reason,
        evidence=evidence,
        sources=sources,
        is_synthetic=is_synthetic,
        warnings=list(dict.fromkeys(warnings)),
    )
