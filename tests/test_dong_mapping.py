import pandas as pd
import pytest

from analytics.area_link import AMBIGUOUS, LINKED
from analytics.dong_mapping import (
    NO_EVIDENCE,
    SUSPECT_CITY,
    SUSPECT_EUPMYEON,
    SUSPECT_FEW,
    build_mapping,
    build_pair_mapping,
    collect_pairs,
    convert_legal_to_admin,
)

# 통·반 단위 인구 예시. 일도이동은 행정동 두 곳에 걸친다고 가정한 가상 자료
POPULATION = pd.DataFrame(
    {
        "legal_dong": ["제주시 건입동", "제주시 건입동", "제주시 일도이동", "제주시 일도이동"],
        "admin_dong": ["제주시 건입동", "제주시 건입동", "제주시 일도2동", "제주시 이도2동"],
        "population": [100, 50, 300, 100],
    }
)


def linked() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "wifi_place_name": ["사라봉공원", "동문 공영주차장", "도두봉", "함덕해변"],
            "users": [10.0, 40.0, 7.0, 5.0],
            "status": [LINKED] * 4,
            "area": ["제주시 건입동", "제주시 일도이동", "제주시 도두일동", "제주시 조천읍"],
            "area_level": ["법정동", "법정동", "법정동", "읍면"],
            "candidates": ["제주시 건입동", "제주시 일도이동", "제주시 도두일동", "제주시 조천읍"],
        }
    )


def test_build_mapping_sums_tong_ban_and_weights():
    mapping = build_mapping(POPULATION).set_index(["legal_dong", "admin_dong"])
    assert mapping.loc[("제주시 건입동", "제주시 건입동"), "population"] == 150
    assert mapping.loc[("제주시 건입동", "제주시 건입동"), "weight"] == 1
    assert mapping.loc[("제주시 일도이동", "제주시 일도2동"), "weight"] == 0.75
    assert mapping.loc[("제주시 일도이동", "제주시 이도2동"), "admin_count"] == 2


def test_zero_population_legal_dong_is_rejected():
    zero = pd.DataFrame(
        {"legal_dong": ["제주시 a동"], "admin_dong": ["제주시 b동"], "population": [0]}
    )
    with pytest.raises(ValueError, match="인구가 0"):
        build_mapping(zero)


def test_convert_default_keeps_split_legal_dong_ambiguous():
    df = convert_legal_to_admin(linked(), build_mapping(POPULATION)).set_index("wifi_place_name")
    assert df.loc["사라봉공원", ["area", "area_level", "conversion"]].tolist() == [
        "제주시 건입동",
        "행정동",
        "1:1 변환",
    ]
    assert df.loc["동문 공영주차장", "status"] == AMBIGUOUS
    assert df.loc["동문 공영주차장", "candidates"] == "제주시 이도2동 / 제주시 일도2동"
    assert df.loc["도두봉", "conversion"] == "변환표 없음"
    assert df.loc["도두봉", "area_level"] == "법정동"
    assert df.loc["함덕해변", "area_level"] == "읍면"
    assert pd.isna(df.loc["함덕해변", "conversion"])
    assert not df["is_estimated"].any()


def test_convert_split_by_population_keeps_total():
    df = convert_legal_to_admin(linked(), build_mapping(POPULATION), split=True)
    split = df[df["conversion"] == "인구 비율 분할"].set_index("area")
    assert split["users"].to_dict() == {"제주시 이도2동": 10.0, "제주시 일도2동": 30.0}
    assert split["is_estimated"].all()
    assert df["users"].sum() == linked()["users"].sum()


class FakeBoundaries:
    """위도 값으로 행정동을 정하는 가짜 경계."""

    def __init__(self, by_lat: dict):
        self.by_lat = by_lat

    def locate(self, lat, lon):
        return self.by_lat.get(float(lat))


def pair_rows(legal: str, admin: str, n: int) -> list[dict]:
    return [
        {"legal_dong": legal, "admin_dong": admin, "place": f"{admin}{i}", "source": "AP"}
        for i in range(n)
    ]


def test_collect_pairs_uses_legal_dong_addresses_only():
    ap = pd.DataFrame(
        {
            "area": ["제주시 노형동", "제주시 애월읍", "제주시 노형동"],
            "latitude": [1.0, 2.0, 9.0],
            "longitude": [0, 0, 0],
            "place_key": ["가", "나", "다"],
        }
    )
    stations = pd.DataFrame(
        {
            "stationAddress": [
                "제주특별자치도 서귀포시 대포동 2309-1",
                "제주시 연동",
                "귀덕리 493-1",
            ],
            "stationName": ["선궷내", "한라병원", "귀덕1리"],
            "latitude": [3.0, 1.0, 2.0],
            "longitude": [0, 0, 0],
        }
    )
    b = FakeBoundaries({1.0: "제주시 노형동", 2.0: "제주시 애월읍", 3.0: "서귀포시 중문동"})
    pairs = collect_pairs(ap, stations, b)
    # 읍면 AP, 행정동 주소 정류소, 경계 밖 AP(9.0)는 빠짐
    assert pairs[["legal_dong", "admin_dong"]].values.tolist() == [
        ["제주시 노형동", "제주시 노형동"],
        ["서귀포시 대포동", "서귀포시 중문동"],
    ]


def test_pair_mapping_suspect_rules():
    pairs = pd.DataFrame(
        pair_rows("제주시 노형동", "제주시 노형동", 10)
        + pair_rows("제주시 노형동", "제주시 구좌읍", 4)
        + pair_rows("제주시 노형동", "제주시 연동", 1)
        + pair_rows("서귀포시 색달동", "서귀포시 예래동", 5)
        + pair_rows("서귀포시 색달동", "제주시 애월읍", 5)
        + pair_rows("제주시 일도일동", "제주시 일도1동", 6)
        + pair_rows("제주시 일도일동", "제주시 이도1동", 3)
        + pair_rows("제주시 회천동", "제주시 봉개동", 1)
    )
    m = build_pair_mapping(pairs).set_index(["legal_dong", "admin_dong"])
    assert m.loc[("제주시 노형동", "제주시 구좌읍"), "suspect_reason"] == SUSPECT_EUPMYEON
    assert m.loc[("제주시 노형동", "제주시 연동"), "suspect_reason"] == SUSPECT_FEW
    assert m.loc[("서귀포시 색달동", "제주시 애월읍"), "suspect_reason"] == (
        f"{SUSPECT_CITY}, {SUSPECT_EUPMYEON}"
    )
    assert m.loc[("제주시 노형동", "제주시 노형동"), "share"] == 10 / 15
    counts = m.groupby(level="legal_dong")["admin_count"].first().to_dict()
    assert counts == {
        "제주시 노형동": 1,
        "서귀포시 색달동": 1,
        "제주시 일도일동": 2,
        "제주시 회천동": 0,
    }

    linked = pd.DataFrame(
        {
            "area": ["제주시 노형동", "제주시 일도일동", "제주시 회천동", "서귀포시 영남동"],
            "area_level": ["법정동"] * 4,
            "status": [LINKED] * 4,
            "users": [1, 2, 3, 4],
        }
    )
    out = convert_legal_to_admin(linked, build_pair_mapping(pairs))
    assert out["conversion"].tolist() == ["1:1 변환", "여러 행정동", NO_EVIDENCE, "변환표 없음"]
    assert out.loc[0, "area"] == "제주시 노형동"
    assert out.loc[1, "status"] == AMBIGUOUS
