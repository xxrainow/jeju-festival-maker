import pandas as pd

from analytics.area_link import AMBIGUOUS, LINKED, NOT_FOUND
from analytics.candidate_compare import (
    ADMIN,
    EXCLUDED,
    LEGAL,
    UNPLACED,
    coverage,
    lodging_frame,
    month_list,
    months_in,
    placement,
    split_totals,
)
from analytics.periods import AnalysisPeriod


def linked() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "area": [
                "제주시 애월읍",
                "제주시 연동",
                "제주시 이도일동",
                None,
                None,
                "제주시 애월읍",
            ],
            "area_level": ["읍면", "행정동", "법정동", None, None, "읍면"],
            "status": [LINKED, LINKED, LINKED, AMBIGUOUS, NOT_FOUND, LINKED],
            "excluded_reason": [None, None, None, None, None, "여러 동을 지나는 길"],
            "users": [10, 20, 30, 40, 50, 60],
        }
    )


def test_months_in():
    assert months_in(AnalysisPeriod("202301", "202412")) == 24
    assert months_in(AnalysisPeriod("202501", "202510")) == 10


def test_placement():
    assert placement(linked()).tolist() == [ADMIN, ADMIN, LEGAL, UNPLACED, UNPLACED, EXCLUDED]


def test_split_totals_keeps_legal_dong_apart_and_skips_exclusions():
    admin, legal = split_totals(linked(), ["users"])
    assert admin["users"].to_dict() == {"제주시 애월읍": 10, "제주시 연동": 20}
    assert legal["users"].to_dict() == {"제주시 이도일동": 30}


def test_coverage_adds_up_to_total():
    row = coverage(linked(), "users", "테스트", "명").iloc[0]
    assert row["전체"] == 210
    assert row[ADMIN] + row[LEGAL] + row[EXCLUDED] + row[UNPLACED] == row["전체"]
    assert coverage(linked(), None, "테스트", "곳").iloc[0]["전체"] == 6


def test_lodging_open_only_and_missing_rooms_kept(tmp_path):
    path = tmp_path / "lodging.csv"
    path.write_text(
        "openStatus,addressJibun,roomCount\n"
        "영업/정상,제주특별자치도 제주시 애월읍 곽지리 1,30\n"
        "영업/정상,제주특별자치도 제주시 이도일동 1315,\n"
        "폐업,제주특별자치도 제주시 애월읍 곽지리 2,99\n"
        "휴업,제주특별자치도 제주시 연동 1,10\n",
        encoding="utf-8-sig",
    )
    df = lodging_frame(path)
    assert len(df) == 2
    assert df["area_level"].tolist() == ["읍면", "법정동"]
    assert df["rooms_missing"].tolist() == [0, 1]
    admin, legal = split_totals(df, ["rooms", "places"])
    assert admin.loc["제주시 애월읍", "rooms"] == 30
    assert legal.loc["제주시 이도일동", "places"] == 1


def test_month_list():
    assert month_list(pd.Series([9, 4, 4, 10])) == "4·9·10월"
