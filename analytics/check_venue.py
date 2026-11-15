"""장소 확인 도구 check_venue의 실제 버전 (agent/fake_checks.py check_venue와 같은 입출력).

기준 (설계 문서 9-3): 카드 지역 안에서 관광객이 모이는 장소가 있고, 걸어갈 수 있는 거리에 버스가 다니는가.

1. 지역(request.region) 안 와이파이 장소 중 관광 사용량 비중이 높은 곳
   (사용량이 너무 적은 장소, 정류소·충전소·올레 코스·공공시설은 뺀다)
2. 장소 좌표(AP 좌표 평균)에서 반경 radius_m(기본 500m) 안 버스 정류소
3. 그 정류소의 하루 평균 이용 인원 (이름 단위, 양방향 합계)

- pass: 반경 안에 이용이 제주 정류소 중앙값 이상인 정류소가 있는 후보 장소가 있음
- conditional: 관광 장소는 있는데 반경 안 정류소가 없거나 이용이 적음 ("셔틀 필요")
- fail: 지역 안 후보 장소가 없음 → suggestion(field="venue")으로 인접 동네 후보
- pending: 지역 없음, 표 없음

행사 시간대 이용·야간 귀가 버스는 시간대 버스 데이터가 들어오면 event_hour_usage, night_return_usage에 붙인다.
지금은 일별 이용으로만 판정하고 evidence에 "대기"로 남긴다.

자료 기간: RECENT_PERIOD(2025-01~2025-10). 아이디어 단계(2023~2024)와 같은 숫자로 고르고 검증하지 않게 한다.
"""

import math
from functools import lru_cache
from pathlib import Path

import pandas as pd

from agent.draft_contracts import CheckResult, IdeaCard, Suggestion, UserRequest
from analytics.periods import RECENT_PERIOD

PROCESSED = Path("data/processed")
PLACES_PATH = PROCESSED / "venue_places.csv"
STATIONS_PATH = PROCESSED / "bus_station_daily.csv"
NEIGHBORS_PATH = PROCESSED / "dong_neighbors.csv"
HOURLY_BUS_PATH = PROCESSED / "bus_station_hourly.csv"  # 시간대 버스 데이터가 오면 여기에

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


def event_hour_usage(station_ids: list[str], hours: list[int]) -> dict | None:
    """행사 시간대(hours) 정류소 이용. 시간대 버스 데이터(HOURLY_BUS_PATH)가 오면 채운다."""
    if not HOURLY_BUS_PATH.exists():
        return None
    raise NotImplementedError("시간대 버스 데이터 형식이 정해지면 구현")


def night_return_usage(
    station_ids: list[str], hours: tuple[int, ...] = (21, 22, 23)
) -> dict | None:
    """야간 귀가 시간대 버스 이용. 시간대 버스 데이터가 오면 채운다."""
    return event_hour_usage(station_ids, list(hours))


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


def candidates_in(area, places, stations, radius_m, low_usage) -> list[dict]:
    """동네 안 장소 → 가까운 정류소. 관광 비중 높은 순, 이용 좋은 정류소가 있는 장소 먼저."""
    rows = places[(places["admin_area"] == area) & ~places["small"]]
    out = []
    near_pool = stations[stations["daily_users"].notna()]
    for r in rows.sort_values("tourism_share_pct", ascending=False).itertuples():
        # 대략 1km 상자로 먼저 거른 뒤 거리 계산
        box = near_pool[
            (near_pool["latitude"].sub(r.latitude).abs() < 0.01)
            & (near_pool["longitude"].sub(r.longitude).abs() < 0.012)
        ]
        dists = [
            (_distance_m(r.latitude, r.longitude, s.latitude, s.longitude), s)
            for s in box.itertuples()
        ]
        within = [(d, s) for d, s in dists if d <= radius_m]
        best = max(within, key=lambda x: x[1].daily_users) if within else None
        nearest = min(dists, key=lambda x: x[0]) if dists else None
        pick = best or nearest
        out.append(
            {
                "name": r.wifi_place_name,
                "admin_area": area,
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
        )
    return sorted(out, key=lambda c: (not c["good_bus"], -c["tourism_share_pct"]))


def check_venue(
    card: IdeaCard,
    request: UserRequest,
    tables=None,
    radius_m: int = RADIUS_M,
) -> CheckResult:
    places, stations, neighbors = load_venue_tables() if tables is None else tables
    region = request.region
    evidence: dict = {"region": region, "radius_m": radius_m, "candidate_places": None}

    def pending(why):
        return CheckResult(check="check_venue", status="pending", reason=why,
                           evidence=evidence, warnings=[why])  # fmt: skip

    if not region:
        return pending("지역이 없어 후보 장소를 찾지 않았어요.")
    if places is None or stations is None:
        return pending(
            "장소·정류소 표가 없어요. uv run python -m analytics.real_checks --build 로 만들어 주세요."
        )
    low_usage = float(stations["daily_users"].median())
    cands = candidates_in(region, places, stations, radius_m, low_usage)
    top = cands[:MAX_CANDIDATES]
    evidence.update(
        {
            "candidate_places": top,
            "low_usage_daily": round(low_usage, 1),
            "night_bus_stops": None,
            "event_hours": {"status": "pending", "reason": "시간대 버스 데이터 대기"},
            "night_return": {"status": "pending", "reason": "시간대 버스 데이터 대기"},
        }
    )
    sources = [places["source"].iloc[0], stations["source"].iloc[0], STATION_SOURCE]
    warnings = [
        (
            f"버스는 {RECENT_PERIOD.label()} 하루 평균 이용이에요. 행사 시간대·야간 귀가 버스는 "
            "시간대 데이터가 들어오면 확인해요."
        ),
        "정류소 이용 인원은 이름 단위라 같은 이름의 양방향 정류소가 합쳐져 있어요.",
        "와이파이 관광 비중은 데이터 사용량 기준이고, 장소 좌표는 AP 설치 위치 평균이에요.",
    ]
    suggestion = None
    names = ", ".join(c["name"] for c in top)
    if any(c["good_bus"] for c in top):
        status = "pass"
        good = top[0]
        reason = (
            f"{region}에 관광객이 모이는 장소가 있고 걸어갈 수 있는 거리에 버스가 다녀요: "
            f"{good['name']} (관광 비중 {good['tourism_share_pct']}%, {good['stop_name']} 정류소 "
            f"{good['stop_distance_m']}m, 하루 {good['stop_daily_users']:,.0f}명)."
        )
    elif top:
        status = "conditional"
        reason = (
            f"{region}에 관광 장소({names})는 있지만 {radius_m}m 안에 이용이 많은 정류소가 없어요. "
            f"{SHUTTLE}해 보여요."
        )
        warnings.append(
            f"{SHUTTLE}: 반경 {radius_m}m 안 정류소가 없거나 하루 이용이 제주 정류소 중앙값({low_usage:,.0f}명) 미만이에요."
        )
    else:
        status = "fail"
        reason = f"{region} 안에서 후보 장소를 찾지 못했어요."
        near = []
        if neighbors is not None:
            for area in neighbors.loc[neighbors["admin_area"] == region, "neighbor"]:
                near += candidates_in(area, places, stations, radius_m, low_usage)
        near = sorted(near, key=lambda c: (not c["good_bus"], -c["tourism_share_pct"]))[
            :MAX_CANDIDATES
        ]
        evidence["neighbor_candidates"] = near
        if near:
            suggestion = Suggestion(
                field="venue",
                value=[
                    {
                        "name": c["name"],
                        "admin_area": c["admin_area"],
                        "reason": f"인접 동네 관광 비중 {c['tourism_share_pct']}%"
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
