import pandas as pd
import pytest

from analytics.area_link import AMBIGUOUS, LINKED
from analytics.dong_mapping import build_mapping, convert_legal_to_admin

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
