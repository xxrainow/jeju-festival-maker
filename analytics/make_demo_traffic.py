"""센터 지정 데이터 교통 3종의 가상 CSV (명세서 컬럼 그대로, 데모·개발용).

- 3-08 도로 노드 정보: road_nodes_demo.csv
- 3-07 도로 구간 정보: road_links_demo.csv
- 3-10 일/시간대별 교통량 정보: traffic_hourly_demo_20250512_20250525.csv.gz (4-11 가상과 같은 2주)

실제 도로망이 아니다. 노드는 허브 버스 정류소 좌표를 약 1km 격자로 솎아 놓고(교차로명칭 자리에 정류소 이름),
구간은 가까운 노드 2곳씩 양방향으로 잇는다. 속도는 제한속도에 시간대 계수(출퇴근·주말 낮 정체)와 잡음을 곱했다.
숫자는 실제 교통량이 아니므로 결과에 is_synthetic=True를 붙인다.

3-05, 3-06(개인 단위)은 쓰지 않는다.

실행: uv run python -m analytics.make_demo_traffic
"""

import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

DEMO_DIR = Path("data/demo")
START, DAYS = date(2025, 5, 12), 14
NODES_PATH = DEMO_DIR / "road_nodes_demo.csv"
LINKS_PATH = DEMO_DIR / "road_links_demo.csv"
TRAFFIC_PATH = DEMO_DIR / "traffic_hourly_demo_20250512_20250525.csv.gz"
GRID_DEG = 0.01  # 약 1km
NEIGHBORS = 2
SEED = 20250512
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

NODE_COLUMNS = ["node_id", "node_name", "latitude", "longitude", "turn_restricted"]
LINK_COLUMNS = [
    "link_id", "start_node_id", "end_node_id", "road_in_use", "lane_count", "road_rating",
    "road_name", "multi_linked", "connect_code", "maximum_speed_limit", "vehicle_restricted",
    "weight_restricted", "height_restricted", "road_type",
]  # fmt: skip
TRAFFIC_COLUMNS = [
    "base_date", "pt_year", "pt_month", "day_of_week", "base_hour", "link_id",
    "average_speed", "average_time",
]  # fmt: skip

# 시간대 계수 (1이면 제한속도의 기본 비율 그대로)
HOUR_FACTOR = {h: 1.0 for h in range(24)} | {7: 0.8, 8: 0.7, 9: 0.8, 17: 0.75, 18: 0.7, 19: 0.8}
WEEKEND_DAY_FACTOR = 0.85  # 토·일 11~17시 관광 정체


def _km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(a))


def make_nodes(stations: pd.DataFrame, rng) -> pd.DataFrame:
    s = stations.copy()
    s["latitude"] = pd.to_numeric(s["latitude"], errors="coerce")
    s["longitude"] = pd.to_numeric(s["longitude"], errors="coerce")
    s = s.dropna(subset=["latitude", "longitude"])
    s["cell"] = (
        (s["latitude"] / GRID_DEG).round().astype(int).astype(str)
        + "_"
        + (s["longitude"] / GRID_DEG).round().astype(int).astype(str)
    )
    s = s.sort_values("stationId").drop_duplicates("cell")
    n = len(s)
    return pd.DataFrame(
        {
            "node_id": [f"40800{i:05d}" for i in range(1, n + 1)],
            "node_name": s["stationName"].to_numpy(),
            "latitude": s["latitude"].round(7).to_numpy(),
            "longitude": s["longitude"].round(7).to_numpy(),
            "turn_restricted": np.where(rng.random(n) < 0.1, "있음", "없음"),
        }
    )


def make_links(nodes: pd.DataFrame, rng) -> pd.DataFrame:
    lat, lon = nodes["latitude"].to_numpy(), nodes["longitude"].to_numpy()
    pairs = set()
    for i in range(len(nodes)):
        d = (lat - lat[i]) ** 2 + ((lon - lon[i]) * 0.84) ** 2  # 경도 1도가 위도보다 짧음
        d[i] = np.inf
        for j in np.argsort(d)[:NEIGHBORS]:
            pairs.add((min(i, j), max(i, j)))
    rows = []
    for k, (i, j) in enumerate(sorted(pairs)):
        lanes = int(rng.choice([1, 2, 3, 4], p=[0.45, 0.35, 0.15, 0.05]))
        rating = {1: "107", 2: "106", 3: "105", 4: "103"}[lanes]
        limit = {1: "50", 2: "60", 3: "70", 4: "70"}[lanes]
        for a, b, direction in ((i, j, 1), (j, i, 2)):
            rows.append(
                {
                    "link_id": f"4080{k + 1:04d}{direction}0",
                    "start_node_id": nodes["node_id"].iloc[a],
                    "end_node_id": nodes["node_id"].iloc[b],
                    "road_in_use": "0",
                    "lane_count": float(lanes),
                    "road_rating": rating,
                    "road_name": f"가상도로{k + 1}",
                    "multi_linked": "0",
                    "connect_code": "000",
                    "maximum_speed_limit": limit,
                    "vehicle_restricted": "0",
                    "weight_restricted": "43200",
                    "height_restricted": "0",
                    "road_type": "000",
                }
            )
    return pd.DataFrame(rows, columns=LINK_COLUMNS)


def make_traffic(nodes: pd.DataFrame, links: pd.DataFrame, rng) -> pd.DataFrame:
    xy = nodes.set_index("node_id")[["latitude", "longitude"]]
    a, b = xy.loc[links["start_node_id"]].to_numpy(), xy.loc[links["end_node_id"]].to_numpy()
    length_m = np.array([_km(*p, *q) * 1000 for p, q in zip(a, b, strict=True)])
    limit = links["maximum_speed_limit"].astype(float).to_numpy()
    base = limit * rng.uniform(0.6, 0.9, len(links))
    frames = []
    for d in range(DAYS):
        day = START + timedelta(days=d)
        weekend = day.weekday() >= 5
        for hour in range(24):
            factor = (
                HOUR_FACTOR[hour]
                if not weekend
                else (WEEKEND_DAY_FACTOR if 11 <= hour <= 17 else 1.0)
            )
            speed = np.clip(base * factor * rng.normal(1, 0.05, len(links)), 5, None)
            frames.append(
                pd.DataFrame(
                    {
                        "base_date": day.strftime("%Y%m%d"),
                        "pt_year": str(day.year),
                        "pt_month": str(day.month),
                        "day_of_week": WEEKDAYS[day.weekday()],
                        "base_hour": f"{hour:02d}",
                        "link_id": links["link_id"].to_numpy(),
                        "average_speed": speed.round().astype(int),
                        "average_time": np.maximum(1, (length_m / (speed / 3.6)).round()).astype(
                            int
                        ),
                    }
                )
            )
    return pd.concat(frames, ignore_index=True)[TRAFFIC_COLUMNS]


def main() -> None:
    from analytics.area_link import load_bus_stations

    rng = np.random.default_rng(SEED)
    nodes = make_nodes(load_bus_stations(), rng)
    links = make_links(nodes, rng)
    traffic = make_traffic(nodes, links, rng)
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    nodes.to_csv(NODES_PATH, index=False, encoding="utf-8-sig")
    links.to_csv(LINKS_PATH, index=False, encoding="utf-8-sig")
    traffic.to_csv(TRAFFIC_PATH, index=False, encoding="utf-8-sig", compression="gzip")
    for p in (NODES_PATH, LINKS_PATH, TRAFFIC_PATH):
        print(f"{p}: {p.stat().st_size / 1024:,.0f} KB")
    print(f"노드 {len(nodes):,}, 구간 {len(links):,}, 교통량 {len(traffic):,}행")


if __name__ == "__main__":
    main()
