"""확인 도구가 쓰는 교통 자료 찾기: 3-10 시간대별 교통량 + 3-07 도로 구간 + 3-08 도로 노드.

- 실데이터: data/raw/ 아래 이름에 키워드가 든 CSV (센터에서 받은 파일, 커밋 제외)
- 없으면 가상 데이터: data/demo/ (analytics.make_demo_traffic, is_synthetic=True)
구간마다 중간점 좌표와 시간대별 평균 속도를 붙여 둔다.
"""

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from analytics import make_demo_traffic as demo

RAW_DIR = Path("data/raw")
REAL_KEYS = {
    "traffic": ("3-10", "교통량"),
    "links": ("3-07", "도로 구간", "도로구간"),
    "nodes": ("3-08", "도로 노드", "도로노드"),
}
SOURCE = "3-10 일/시간대별 교통량, 3-07 도로 구간, 3-08 도로 노드"


@dataclass
class TrafficData:
    links: pd.DataFrame  # link_id, road_name, mid_lat, mid_lon
    hourly: pd.DataFrame  # link_id, weekend, hour, average_speed (평균)
    is_synthetic: bool

    @property
    def label(self) -> str:
        return SOURCE + (" (가상 데이터 2025-05-12~25)" if self.is_synthetic else "")


def _find(keys) -> Path | None:
    hits = sorted(
        p for p in RAW_DIR.glob("*.csv*")
        if any(k in unicodedata.normalize("NFC", p.name) for k in keys)
    )  # fmt: skip
    return hits[-1] if hits else None


def find_traffic_files() -> tuple[dict[str, Path], bool] | None:
    real = {k: _find(v) for k, v in REAL_KEYS.items()}
    if all(real.values()):
        return real, False
    files = {"traffic": demo.TRAFFIC_PATH, "links": demo.LINKS_PATH, "nodes": demo.NODES_PATH}
    return (files, True) if all(p.exists() for p in files.values()) else None


def prepare(traffic: pd.DataFrame, links: pd.DataFrame, nodes: pd.DataFrame, synthetic: bool):
    nodes = nodes.assign(
        latitude=pd.to_numeric(nodes["latitude"]), longitude=pd.to_numeric(nodes["longitude"])
    ).set_index("node_id")
    a = nodes.loc[links["start_node_id"], ["latitude", "longitude"]].to_numpy()
    b = nodes.loc[links["end_node_id"], ["latitude", "longitude"]].to_numpy()
    out_links = pd.DataFrame(
        {
            "link_id": links["link_id"].to_numpy(),
            "road_name": links["road_name"].to_numpy(),
            "mid_lat": (a[:, 0] + b[:, 0]) / 2,
            "mid_lon": (a[:, 1] + b[:, 1]) / 2,
        }
    )
    t = traffic.assign(
        hour=pd.to_numeric(traffic["base_hour"]),
        weekend=traffic["day_of_week"].isin(["토", "일"]),
        average_speed=pd.to_numeric(traffic["average_speed"]),
    )
    hourly = t.groupby(["link_id", "weekend", "hour"], as_index=False)["average_speed"].mean()
    return TrafficData(out_links, hourly, synthetic)


@lru_cache(maxsize=1)
def load_traffic() -> TrafficData | None:
    found = find_traffic_files()
    if found is None:
        return None
    files, synthetic = found
    read = {"dtype": str, "encoding": "utf-8-sig"}
    return prepare(
        pd.read_csv(files["traffic"], **read),
        pd.read_csv(files["links"], **read),
        pd.read_csv(files["nodes"], **read),
        synthetic,
    )
