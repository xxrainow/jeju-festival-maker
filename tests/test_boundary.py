import json

import pytest

from analytics.boundary import Boundaries, load_jeju_boundaries


def square(name: str, code: str, x0: float, y0: float) -> dict:
    ring = [[x0, y0], [x0 + 1, y0], [x0 + 1, y0 + 1], [x0, y0 + 1], [x0, y0]]
    return {
        "type": "Feature",
        "properties": {"adm_nm": f"제주특별자치도 {name}", "adm_cd2": code},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


FEATURES = [
    square("제주시 일도1동", "5011051000", 126.0, 33.0),
    square("서귀포시 남원읍", "5013025000", 127.0, 33.0),
]


def test_locate_point_inside_boundary():
    b = Boundaries(FEATURES)
    assert b.locate(33.5, 126.5) == "제주시 일도1동"
    assert b.locate("33.5", "127.5") == "서귀포시 남원읍"


def test_outside_or_missing_coordinates_are_not_guessed():
    b = Boundaries(FEATURES)
    assert b.locate(35.0, 126.5) is None  # 경계 밖은 가까운 동으로 붙이지 않음
    assert b.locate(float("nan"), 126.5) is None
    assert b.locate(None, None) is None


def test_load_keeps_only_jeju(tmp_path):
    other = square("서울특별시 종로구 청운효자동", "1111051500", 126.0, 37.0)
    path = tmp_path / "b.geojson"
    path.write_text(json.dumps({"features": [*FEATURES, other]}), encoding="utf-8")
    assert sorted(load_jeju_boundaries(path).areas) == ["서귀포시 남원읍", "제주시 일도1동"]


def test_load_without_jeju_fails(tmp_path):
    path = tmp_path / "b.geojson"
    path.write_text(json.dumps({"features": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="제주"):
        load_jeju_boundaries(path)
