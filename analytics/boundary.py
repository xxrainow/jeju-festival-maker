"""행정동 경계로 좌표가 어느 행정동·읍면 안에 있는지 판정한다.

경계 파일: vuski/admdongkor ver20261001 (통계청 SGIS 행정동 경계 기반, CC BY 4.0)
https://github.com/vuski/admdongkor → data/raw/boundary/HangJeongDong_ver20261001.geojson
경계 밖(해안선 바깥 등) 좌표는 가장 가까운 동으로 붙이지 않고 None으로 둔다.
"""

import json
import math
from pathlib import Path

from shapely import Point, STRtree
from shapely.geometry import shape

BOUNDARY_PATH = Path("data/raw/boundary/HangJeongDong_ver20261001.geojson")
JEJU_CODE_PREFIX = "50"  # 행정안전부 행정기관코드 앞 두 자리


class Boundaries:
    def __init__(self, features: list[dict]):
        self.areas = [f["properties"]["adm_nm"].removeprefix("제주특별자치도 ") for f in features]
        self.geoms = [shape(f["geometry"]) for f in features]
        self.tree = STRtree(self.geoms)

    def locate(self, latitude, longitude) -> str | None:
        """`시 행정동` 또는 `시 읍면`. 좌표가 없거나 경계 밖이면 None."""
        try:
            lat, lon = float(latitude), float(longitude)
        except (TypeError, ValueError):
            return None
        if math.isnan(lat) or math.isnan(lon):
            return None
        hits = self.tree.query(Point(lon, lat), predicate="within")
        return self.areas[hits[0]] if len(hits) == 1 else None


def load_jeju_boundaries(path: Path = BOUNDARY_PATH) -> Boundaries:
    data = json.loads(path.read_text(encoding="utf-8"))
    features = [
        f for f in data["features"] if f["properties"]["adm_cd2"].startswith(JEJU_CODE_PREFIX)
    ]
    if not features:
        raise ValueError("경계 파일에 제주 행정동이 없습니다")
    return Boundaries(features)
