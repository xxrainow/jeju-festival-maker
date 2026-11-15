import numpy as np
import pandas as pd

from analytics import make_demo_traffic as demo
from analytics.check_risk import congestion_check
from analytics.traffic_source import prepare

STATIONS = pd.DataFrame(
    {
        "stationId": [f"40600{i:04d}" for i in range(6)],
        "stationName": [f"정류소{i}" for i in range(6)],
        "latitude": ["33.50", "33.50", "33.52", "33.54", "33.56", "33.5001"],
        "longitude": ["126.50", "126.52", "126.52", "126.54", "126.56", "126.5001"],
    }
)


def demo_tables():
    rng = np.random.default_rng(1)
    nodes = demo.make_nodes(STATIONS, rng)
    links = demo.make_links(nodes, rng)
    return nodes, links, demo.make_traffic(nodes, links, rng)


def test_demo_traffic_follows_spec_columns():
    nodes, links, traffic = demo_tables()
    assert list(nodes.columns) == demo.NODE_COLUMNS
    assert list(links.columns) == demo.LINK_COLUMNS
    assert list(traffic.columns) == demo.TRAFFIC_COLUMNS
    assert len(nodes) == 5  # 같은 1km 칸의 정류소는 하나로
    assert nodes["node_id"].str.len().eq(10).all() and links["link_id"].str.len().eq(10).all()
    assert traffic["base_date"].nunique() == demo.DAYS
    assert sorted(traffic["base_hour"].unique()) == [f"{h:02d}" for h in range(24)]
    assert set(traffic["day_of_week"]) == set(demo.WEEKDAYS)
    assert (traffic["average_speed"] > 0).all() and (traffic["average_time"] > 0).all()


def test_congestion_check_compares_event_hours_with_usual():
    nodes, links, traffic = demo_tables()
    data = prepare(traffic.astype(str), links, nodes.astype(str), synthetic=True)
    point = [{"name": "장소", "lat": 33.50, "lon": 126.51}]
    r = congestion_check(point, data)
    assert r["is_synthetic"] and r["links_checked"] > 0 and "가상 데이터" in r["source"]
    # 주말 행사 시간대만 아주 느리게 바꾸면 정체
    slow = traffic.copy()
    weekend = slow["day_of_week"].isin(["토", "일"]) & slow["base_hour"].astype(int).between(11, 19)
    slow.loc[weekend, "average_speed"] = 5
    r = congestion_check(point, prepare(slow.astype(str), links, nodes.astype(str), True))
    assert r["status"] == "conditional" and r["slow_links"][0]["ratio"] < 0.8
    assert congestion_check([], data) is None
    far = congestion_check([{"name": "먼 곳", "lat": 33.2, "lon": 126.2}], data)
    assert far["links_checked"] == 0 and far["status"] == "pass"
