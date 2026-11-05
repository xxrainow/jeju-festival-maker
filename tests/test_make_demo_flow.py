import pandas as pd

from analytics.flow_spec import AGE_CODES, COLUMNS, DEMO_DISTRICT_BY_EMD, DISTRICTS, EMD_CODES
from analytics.make_demo_flow import build_demo


def demo() -> pd.DataFrame:
    # 2025-05-16(금) ~ 05-17(토): 평일 하루, 주말 하루
    from datetime import date

    return build_demo(start=date(2025, 5, 16), days=2)


def test_columns_and_all_combinations():
    df = demo()
    assert df.columns.tolist() == COLUMNS
    assert len(df) == 2 * 24 * 43 * 2 * 14 * 2
    assert set(df["emd_cd"]) == set(EMD_CODES)
    assert set(df["age"]) == set(AGE_CODES)
    assert set(df["time"]) == {str(h) for h in range(1, 25)}
    assert set(df["dstrct_se"]) <= set(DISTRICTS)
    assert set(DEMO_DISTRICT_BY_EMD) == set(EMD_CODES.values())
    assert (df.dtypes == object).all()  # 명세처럼 모두 문자열
    assert df["visit_pop_cnt"].str.fullmatch(r"\d+\.\d{4}").all()


def test_same_seed_same_data():
    assert demo().equals(demo())


def test_demo_patterns():
    df = demo()
    df["visit"] = df["visit_pop_cnt"].astype(float)
    by_day = df.groupby("base_date")["visit"].sum()
    assert by_day["20250517"] > by_day["20250516"] * 1.2  # 주말 방문 증가

    by_hour = df.groupby(df["time"].astype(int))["visit"].sum()
    assert by_hour[14] > by_hour[3] * 3  # 낮 시간대 방문 증가

    outside = df[df["resd"] == "그외"].groupby("emd_nm")["visit"].sum()
    share = outside / df.groupby("emd_nm")["visit"].sum()
    assert (
        share["서귀포시 성산읍"] > share["제주시 삼도2동"] * 2
    )  # 관광지 많은 동네는 그외 비율 높음
