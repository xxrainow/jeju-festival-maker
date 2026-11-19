"""장소 확인 도구 check_venue의 실제 버전 (agent/fake_checks.py check_venue와 같은 입출력).

기준 (설계 문서 9-3): 카드 지역 안에서 관광객이 모이는 장소가 있고, 걸어갈 수 있는 거리에 버스가 다니는가.

1. 지역(request.region) 안 와이파이 장소 중 관광 사용량 비중이 높은 곳
   (사용량이 너무 적은 장소, 정류소·충전소·올레 코스·공공시설은 뺀다)
2. 장소 좌표(AP 좌표 평균)에서 반경 radius_m(기본 500m) 안 버스 정류소
3. 그 정류소의 하루 평균 이용 인원 (이름 단위, 양방향 합계)

- pass: 반경 안에 이용이 제주 정류소 중앙값 이상인 정류소가 있는 후보 장소가 있음
- conditional: 관광 장소는 있는데 반경 안 정류소가 없거나 이용이 적음 ("셔틀 필요")
- fail: 지역 안 후보 장소가 없음 → suggestion(field="venue")으로 인접 동네 후보 (동네 중심에서 가까운 순)
- pending: 지역 없음, 표 없음

카드에 장소(card.venue)가 정해져 있으면(에이전트가 인접 동네 후보로 바꿨거나 사용자가 직접 고름)
그 장소 기준으로 같은 규칙(반경 정류소·이용 인원)으로 판정한다. 장소가 인접 동네에 있어도 된다.

행사 시간대 이용·야간 귀가 버스: 3-04 정류소별 시간대 이용(실데이터가 없으면 가상 데이터)으로 후보 정류소의
승차 인원을 evidence(event_hours, night_return)에 보여준다. 판정은 일별 이용(실데이터)으로만 해서 결과는
is_synthetic=False이고, 가상 데이터 부분은 evidence의 data_label로 표시한다.
야간 귀가 참고 경고는 허브 일별 시간대별 승차(실데이터)의 제주 전체 22~24시 비중을 쓴다.

자료 기간: RECENT_PERIOD(2025-01~2025-10). 아이디어 단계(2023~2024)와 같은 숫자로 고르고 검증하지 않게 한다.
"""

import math
from functools import lru_cache
from pathlib import Path

import pandas as pd

from agent.draft_contracts import CheckResult, IdeaCard, Suggestion, UserRequest
from analytics.bus_hourly import NIGHT_HOURS
from analytics.check_timing import ADMIN_BUILD_NOTE
from analytics.periods import RECENT_PERIOD

PROCESSED = Path("data/processed")
PLACES_PATH = PROCESSED / "venue_places.csv"
STATIONS_PATH = PROCESSED / "bus_station_daily.csv"
NEIGHBORS_PATH = PROCESSED / "dong_neighbors.csv"
EVENT_HOURS = tuple(range(11, 20))  # 행사 시간대 11~19시 (check_risk 정체와 같음)
NIGHT_FEW = 1.0  # 야간 귀가(21~23시) 하루 승차가 이보다 적으면 경고

RADIUS_M = 500
MAX_CANDIDATES = 3
MIN_USE_QUANTILE = 0.25  # 제주 장소 사용량 하위 25% 미만은 후보에서 뺌 (작은 장소의 비중 튐 방지)
EXCLUDED_CATEGORIES = {"버스정류소", "전기차충전소", "올레·코스"}
WIFI_SOURCE = "와이파이 장소별 방문자별 사용량"
BUS_SOURCE = "이용자유형별 버스정류소 이용인원"
STATION_SOURCE = "제주데이터허브 버스 정류소 위치"
SHUTTLE = "셔틀 필요"


# ---------- 표 만들기 ----------


def build_places(usage: pd.DataFrame, places: pd.DataFrame) -> pd.DataFrame:
    """동네 안 장소별 관광 사용량 비중 (RECENT_PERIOD, 방문유형 있는 사용량 기준)."""
    from research.materials import EXCLUDED_PLACE

    u = RECENT_PERIOD.filter_months(usage)
    u = u[u["visit_type"].notna()]
    total = u.groupby("wifi_place_name")["use_amount"].sum().astype(float)
    tour = u[u["visit_type"] == "관광"].groupby("wifi_place_name")["use_amount"].sum()
    out = places.join(total.rename("total_use"), on="wifi_place_name").join(
        tour.astype(float).rename("tourism_use"), on="wifi_place_name"
    )
    out = out[out["total_use"] > 0].fillna({"tourism_use": 0.0})
    out = out[~out["category"].isin(EXCLUDED_CATEGORIES)]
    out = out[~out["wifi_place_name"].str.contains(EXCLUDED_PLACE)]
    out = out[out["latitude"].notna()]
    out["tourism_share_pct"] = (out["tourism_use"] / out["total_use"] * 100).round(1)
    out["small"] = out["total_use"] < out["total_use"].quantile(MIN_USE_QUANTILE)
    out["source"] = f"{WIFI_SOURCE} {RECENT_PERIOD.label()}"
    return out.reset_index(drop=True)


def build_station_daily(bus_data: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """정류소(ID, 좌표)마다 하루 평균 이용 인원. 이용 자료는 이름 단위라 같은 이름(양방향)은 같은 값."""
    days = bus_data["base_date"].nunique()
    per_key = bus_data.groupby("station_key")["user_count"].sum() / days
    out = stations[
        ["stationId", "stationName", "latitude", "longitude", "area", "station_key"]
    ].copy()
    out["latitude"] = pd.to_numeric(out["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(out["longitude"], errors="coerce")
    out["daily_users"] = out["station_key"].map(per_key).round(1)
    out["days"] = days
    out["source"] = f"{BUS_SOURCE} {RECENT_PERIOD.label()}"
    return out[out["latitude"].notna()].reset_index(drop=True)


def build_neighbors(boundaries) -> pd.DataFrame:
    """경계가 맞닿은 동네 짝."""
    rows = []
    for i, a in enumerate(boundaries.areas):
        for j, b in enumerate(boundaries.areas):
            if i != j and boundaries.geoms[i].buffer(1e-4).intersects(boundaries.geoms[j]):
                rows.append((a, b))
    return pd.DataFrame(rows, columns=["admin_area", "neighbor"])


# ---------- 시간대 버스 (데이터 대기) ----------


def event_hour_usage(station_ids: list[str], hours=EVENT_HOURS, data=...) -> dict | None:
    """행사 시간대(hours) 정류소 하루 평균 승차 (3-04). 자료가 없으면 None."""
    from analytics.bus_hourly import boarding_by_hours

    return boarding_by_hours(station_ids, hours, data)


def night_return_usage(station_ids: list[str], hours=NIGHT_HOURS, data=...) -> dict | None:
    """야간 귀가(21~23시) 정류소 하루 평균 승차 (3-04). 자료가 없으면 None."""
    from analytics.bus_hourly import boarding_by_hours

    return boarding_by_hours(station_ids, hours, data)


def hourly_evidence(top: list[dict], hourly=...) -> tuple[dict, dict, list[str]]:
    """후보 정류소별 행사 시간대·야간 귀가 승차. (event_hours, night_return, 경고)."""
    from analytics.bus_hourly import night_share_warning

    warnings = []
    if night := night_share_warning():
        warnings.append(night)
    rows_e, rows_n, label = [], [], None
    for c in top:
        if not c.get("stop_id"):
            continue
        e = event_hour_usage([c["stop_id"]], data=hourly)
        n = night_return_usage([c["stop_id"]], data=hourly)
        if e is None or n is None:
            break
        label = e
        rows_e.append({"name": c["name"], "stop_name": c["stop_name"],
                       "daily_boarding": e["daily_boarding"], "share_pct": e["share_pct"]})  # fmt: skip
        rows_n.append({"name": c["name"], "stop_name": c["stop_name"],
                       "daily_boarding": n["daily_boarding"], "share_pct": n["share_pct"]})  # fmt: skip
    if label is None:
        waiting = {"status": "pending", "reason": "시간대 버스 데이터 없음"}
        return waiting, dict(waiting), warnings
    meta = {"source": label["source"], "is_synthetic": label["is_synthetic"],
            "data_label": label["data_label"]}  # fmt: skip
    event = {"hours": f"{EVENT_HOURS[0]}~{EVENT_HOURS[-1]}시", "stops": rows_e, **meta}
    night = {"hours": f"{NIGHT_HOURS[0]}~{NIGHT_HOURS[-1]}시", "stops": rows_n, **meta}
    tag = f" ({label['data_label']})" if label["is_synthetic"] else ""
    few = [r for r in rows_n if r["daily_boarding"] < NIGHT_FEW]
    if few:
        names = ", ".join(f"{r['name']}({r['stop_name']})" for r in few)
        warnings.append(
            f"야간 귀가({night['hours']}) 하루 승차가 {NIGHT_FEW:.0f}명 미만인 후보 정류소: {names}{tag}. 귀가 셔틀을 검토해 주세요."
        )
    if label["is_synthetic"]:
        warnings.append(
            "행사 시간대·야간 귀가 정류소 승차는 3-04 가상 데이터예요. 판정은 일별 이용(실데이터)으로만 했어요."
        )
    return event, night, warnings


# ---------- 판정 ----------


def _distance_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def load_venue_tables():
    from analytics.reference_data import reference_first

    def read(path):
        path = reference_first(path.name, path)  # analytics/reference/ 먼저
        return (
            pd.read_csv(path, encoding="utf-8-sig", dtype={"stationId": str})
            if path.exists()
            else None
        )

    return read(PLACES_PATH), read(STATIONS_PATH), read(NEIGHBORS_PATH)


def _place_candidate(r, stations, radius_m, low_usage) -> dict:
    """장소 한 곳 → 반경 안 정류소 중 이용이 가장 많은 곳 (없으면 가장 가까운 곳)."""
    near_pool = stations[stations["daily_users"].notna()]
    # 대략 1km 상자로 먼저 거른 뒤 거리 계산
    box = near_pool[
        (near_pool["latitude"].sub(r.latitude).abs() < 0.01)
        & (near_pool["longitude"].sub(r.longitude).abs() < 0.012)
    ]
    dists = [
        (_distance_m(r.latitude, r.longitude, s.latitude, s.longitude), s) for s in box.itertuples()
    ]
    within = [(d, s) for d, s in dists if d <= radius_m]
    best = max(within, key=lambda x: x[1].daily_users) if within else None
    nearest = min(dists, key=lambda x: x[0]) if dists else None
    pick = best or nearest
    return {
        "name": r.wifi_place_name,
        "admin_area": r.admin_area,
        "latitude": round(r.latitude, 6),
        "longitude": round(r.longitude, 6),
        "tourism_share_pct": r.tourism_share_pct,
        "stop_name": pick[1].stationName if pick else None,
        "stop_id": pick[1].stationId if pick else None,
        "stop_distance_m": round(pick[0]) if pick else None,
        "stop_daily_users": float(pick[1].daily_users) if pick else None,
        "stops_within_radius": len(within),
        "good_bus": bool(best and best[1].daily_users >= low_usage),
    }


def candidates_in(area, places, stations, radius_m, low_usage) -> list[dict]:
    """동네 안 장소 → 가까운 정류소. 관광 비중 높은 순, 이용 좋은 정류소가 있는 장소 먼저."""
    rows = places[(places["admin_area"] == area) & ~places["small"]]
    out = [
        _place_candidate(r, stations, radius_m, low_usage)
        for r in rows.sort_values("tourism_share_pct", ascending=False).itertuples()
    ]
    return sorted(out, key=lambda c: (not c["good_bus"], -c["tourism_share_pct"]))


def chosen_candidates(card, places, stations, radius_m, low_usage) -> list[dict]:
    """카드에 정해진 장소(에이전트·사용자가 고름)를 장소 표에서 찾아 같은 규칙으로 판정할 후보로.

    인접 동네 장소여도 된다. 표에 없는 이름은 뺀다.
    """
    out = []
    for v in card.venue:
        rows = places[places["wifi_place_name"] == v.name]
        if v.admin_area and (rows["admin_area"] == v.admin_area).any():
            rows = rows[rows["admin_area"] == v.admin_area]
        if not rows.empty:
            out.append(_place_candidate(next(rows.itertuples()), stations, radius_m, low_usage))
    return out


@lru_cache(maxsize=1)
def _default_centroids() -> dict:
    from analytics.check_timing import _centroids, load_timing_data

    return _centroids(load_timing_data().station_by_dong)


def _with_distance(cands: list[dict], region: str, centroids: dict) -> list[dict]:
    """원래 동네 중심에서 각 후보까지 거리(km)를 붙인다. 중심 좌표가 없으면 None."""
    center = centroids.get(region)
    for c in cands:
        c["distance_km"] = (
            round(_distance_m(center[0], center[1], c["latitude"], c["longitude"]) / 1000, 1)
            if center
            else None
        )
    return cands


def check_venue(
    card: IdeaCard,
    request: UserRequest,
    tables=None,
    radius_m: int = RADIUS_M,
    hourly=...,
    centroids: dict | None = None,
) -> CheckResult:
    places, stations, neighbors = load_venue_tables() if tables is None else tables
    region = request.region
    evidence: dict = {"region": region, "radius_m": radius_m, "candidate_places": None}

    def pending(why, *extra):
        return CheckResult(check="check_venue", status="pending", reason=why,
                           evidence=evidence, warnings=[why, *extra])  # fmt: skip

    if not region:
        return pending("지역이 없어 후보 장소를 찾지 않았어요.")
    if places is None or stations is None:
        return pending(
            "장소·정류소 표가 아직 없어요. 관리자에게 표 만들기를 요청해 주세요.",
            ADMIN_BUILD_NOTE,
        )
    low_usage = float(stations["daily_users"].median())
    centroids = _default_centroids() if centroids is None else centroids
    cands = candidates_in(region, places, stations, radius_m, low_usage)
    # 원래 동네에 후보가 없으면 인접 동네 후보를 동네 중심에서 가까운 순으로 (화면 선택지·제안에 씀)
    near = []
    if not cands and neighbors is not None:
        for area in neighbors.loc[neighbors["admin_area"] == region, "neighbor"]:
            near += candidates_in(area, places, stations, radius_m, low_usage)
        near = _with_distance(near, region, centroids)
        near = sorted(near, key=lambda c: (c["distance_km"] is None, c["distance_km"] or 0,
                                           -c["tourism_share_pct"]))[:MAX_CANDIDATES]  # fmt: skip
        evidence["neighbor_candidates"] = near
    chosen = chosen_candidates(card, places, stations, radius_m, low_usage)
    if chosen:  # 카드에 장소가 정해져 있으면 그 장소 기준으로 판정
        chosen = _with_distance(chosen, region, centroids)
        cands = sorted(chosen, key=lambda c: (not c["good_bus"], -c["tourism_share_pct"]))
        evidence["chosen_venue"] = True
    top = cands[:MAX_CANDIDATES]
    evidence.update(
        {
            "candidate_places": top,
            "low_usage_daily": round(low_usage, 1),
            "night_bus_stops": None,
        }
    )
    event, night, hour_warnings = hourly_evidence(top, hourly)
    evidence["event_hours"], evidence["night_return"] = event, night
    sources = [places["source"].iloc[0], stations["source"].iloc[0], STATION_SOURCE]
    warnings = [
        f"판정은 버스 {RECENT_PERIOD.label()} 하루 평균 이용으로 했어요.",
        "정류소 이용 인원은 이름 단위라 같은 이름의 양방향 정류소가 합쳐져 있어요.",
        "와이파이 관광 비중은 데이터 사용량 기준이고, 장소 좌표는 AP 설치 위치 평균이에요.",
        *hour_warnings,
    ]
    if event.get("source"):
        sources.append(event["source"])
    suggestion = None
    names = ", ".join(c["name"] for c in top)
    if chosen:
        where = f"고른 장소({names})"
        outside = sorted({c["admin_area"] for c in top if c["admin_area"] != region})
        if outside:
            where += f"는 {region} 인접 동네({', '.join(outside)})에 있어요. 이 장소"
    else:
        where = f"{region}"
    if any(c["good_bus"] for c in top):
        status = "pass"
        good = top[0]
        lead = (
            f"{where} 근처에 걸어갈 수 있는 거리에 버스가 다녀요"
            if chosen
            else f"{region}에 관광객이 모이는 장소가 있고 걸어갈 수 있는 거리에 버스가 다녀요"
        )
        reason = (
            f"{lead}: "
            f"{good['name']} (관광 비중 {good['tourism_share_pct']}%, {good['stop_name']} 정류소 "
            f"{good['stop_distance_m']}m, 하루 {good['stop_daily_users']:,.0f}명)."
        )
    elif top:
        status = "conditional"
        lead = f"{where} 근처" if chosen else f"{region}에 관광 장소({names})는 있지만"
        reason = f"{lead} {radius_m}m 안에 이용이 많은 정류소가 없어요. {SHUTTLE}해 보여요."
        warnings.append(
            f"{SHUTTLE}: 반경 {radius_m}m 안 정류소가 없거나 하루 이용이 제주 정류소 중앙값({low_usage:,.0f}명) 미만이에요."
        )
    else:
        status = "fail"
        reason = f"{region} 안에서 후보 장소를 찾지 못했어요."
        if near:
            reason += f" 인접 동네 후보 {len(near)}곳이 있어요."
            suggestion = Suggestion(
                field="venue",
                value=[
                    {
                        "name": c["name"],
                        "admin_area": c["admin_area"],
                        "reason": f"인접 동네 관광 비중 {c['tourism_share_pct']}%"
                        + (f", 동네 중심에서 약 {c['distance_km']}km" if c["distance_km"] else "")
                        + (
                            f", {c['stop_name']} 정류소 {c['stop_distance_m']}m"
                            if c["stop_name"]
                            else ""
                        ),
                    }
                    for c in near
                ],
                why=f"{region} 안에 후보 장소가 없어 인접 동네 후보로 바꿔요.",
            )
    return CheckResult(
        check="check_venue",
        status=status,
        reason=reason,
        evidence=evidence,
        sources=sources,
        suggestion=suggestion,
        is_synthetic=False,
        warnings=warnings,
    )
