from datetime import date

import pandas as pd

from analytics.loaders import (
    aggregate_wifi_usage,
    bus_exclusion_notes,
    load_bus_usage,
    load_festivals,
    load_visitor_trend,
    load_wifi_usage,
    load_wifi_users,
    normalize_station_name,
    strip_ap_number,
)

BUS_HEADER = "﻿base_date,station_name,user_type,user_count\n"


def write(path, text, encoding="utf-8"):
    path.write_text(text, encoding=encoding)
    return path


# 버스 이용 인원


def test_bus_station_name_with_unquoted_commas(tmp_path):
    path = write(
        tmp_path / "bus.csv",
        BUS_HEADER
        + "20190101,제주국제공항(대정,화순,일주서로),일반,92\n"
        + "20190101,거슨새미오름,안돌오름,어린이,2\n"
        + "20190101,한라병원,일반,10\n",
    )
    df = load_bus_usage(path)
    assert set(df["station_name"]) == {
        "제주국제공항(대정,화순,일주서로)",
        "거슨새미오름,안돌오름",
        "한라병원",
    }
    assert df["user_count"].sum() == 104


def test_bus_abnormal_dates_are_excluded(tmp_path):
    path = write(
        tmp_path / "bus.csv",
        BUS_HEADER
        + "20211222,한라병원,일반,100\n"
        + "20211223,한라병원,일반,17\n"
        + "20221127,한라병원,일반,30\n"
        + "20221201,한라병원,일반,90\n",
    )
    df = load_bus_usage(path)
    assert df["base_date"].tolist() == [date(2021, 12, 22), date(2022, 12, 1)]


def test_bus_date_filter(tmp_path):
    path = write(
        tmp_path / "bus.csv",
        BUS_HEADER
        + "20240101,한라병원,일반,1\n20240102,한라병원,일반,2\n20240103,한라병원,일반,3\n",
    )
    df = load_bus_usage(path, start=date(2024, 1, 2), end=date(2024, 1, 2))
    assert df["user_count"].tolist() == [2]


def test_bus_exclusion_notes_mention_missing_period():
    notes = " ".join(bus_exclusion_notes())
    assert "2022-08-12 ~ 2022-11-23" in notes
    assert "2021-12-23" in notes


def test_bus_renamed_station_shares_key(tmp_path):
    path = write(
        tmp_path / "bus.csv",
        BUS_HEADER
        + "20241006,제주국제공항4(대정,화순,일주서로),일반,10\n"
        + "20241007,제주국제공항4(대정화순일주서로),일반,12\n",
    )
    df = load_bus_usage(path)
    assert df["station_key"].nunique() == 1
    assert df["station_name"].nunique() == 2


def test_normalize_station_name():
    assert (
        normalize_station_name("제주국제공항 4 (대정, 화순·일주서로)")
        == "제주국제공항4(대정화순일주서로)"
    )


def test_bus_closed_station_is_kept(tmp_path):
    path = write(tmp_path / "bus.csv", BUS_HEADER + "20190101,(구)동홍동주민센터,경로,3\n")
    assert load_bus_usage(path)["station_name"].tolist() == ["(구)동홍동주민센터"]


# 와이파이


WIFI_USERS_HEADER = "base_year_month,sex,age_range,wifi_place_name,user_count\n"
WIFI_USAGE_HEADER = "base_year_month,quarter,sex,age_range,visit_type,wifi_place_name,use_amount\n"


def test_wifi_users_only_from_2020_10(tmp_path):
    path = write(
        tmp_path / "users.csv",
        WIFI_USERS_HEADER + "202009,남성,10대,4코스,100\n202010,남성,10대,4코스,50\n",
    )
    assert load_wifi_users(path)["base_year_month"].tolist() == ["202010"]


def test_wifi_user_count_strips_non_digits(tmp_path):
    path = write(
        tmp_path / "users.csv",
        WIFI_USERS_HEADER + "202105,여성,50대,버스정류소_삼아아파트[남],1012`\n",
    )
    assert load_wifi_users(path)["user_count"].tolist() == [1012]


def test_strip_ap_number():
    assert strip_ap_number("함덕 서우봉 해변 #1") == "함덕 서우봉 해변"
    assert strip_ap_number("한라생태숲 #2-3") == "한라생태숲"
    assert strip_ap_number("헌마공신 김만일기념관_체험실_#1") == "헌마공신 김만일기념관_체험실"
    assert strip_ap_number("4코스") == "4코스"


def test_wifi_usage_null_visit_type_is_missing(tmp_path):
    path = write(
        tmp_path / "usage.csv",
        WIFI_USAGE_HEADER
        + "202010,4분기,남성,20대,NULL,1-29호어린이공원,152643\n"
        + "202010,4분기,남성,20대,관광,1-29호어린이공원,100\n",
    )
    df = load_wifi_usage(path)
    assert df["visit_type"].isna().tolist() == [True, False]


def test_wifi_usage_aggregates_by_place_month_type(tmp_path):
    path = write(
        tmp_path / "usage.csv",
        WIFI_USAGE_HEADER
        + "202001,1분기,남성,20대,,함덕 서우봉 해변 #1,999\n"
        + "202101,1분기,남성,20대,관광,함덕 서우봉 해변 #1,10\n"
        + "202101,1분기,여성,30대,관광,함덕 서우봉 해변 #2,20\n"
        + "202101,1분기,여성,30대,거주,함덕 서우봉 해변 #2,5\n",
    )
    summary = aggregate_wifi_usage(load_wifi_usage(path))
    assert summary.to_dict("records") == [
        {
            "wifi_place_name": "함덕 서우봉 해변",
            "base_year_month": "202101",
            "visit_type": "거주",
            "use_amount": 5,
        },
        {
            "wifi_place_name": "함덕 서우봉 해변",
            "base_year_month": "202101",
            "visit_type": "관광",
            "use_amount": 30,
        },
    ]


# 내국인 유동인구 추이


TREND_HEADER = "﻿base_year_month,sex,age_range,time_range,visit_population_count\n"


def test_visitor_trend_24h_becomes_00h(tmp_path):
    path = write(tmp_path / "trend.csv", TREND_HEADER + "202201,남성,10대,24시,10.5\n")
    assert load_visitor_trend(path)["time_range"].tolist() == ["00시"]


def test_visitor_trend_duplicate_rows_are_summed(tmp_path):
    path = write(
        tmp_path / "trend.csv",
        TREND_HEADER
        + "202201,남성,70대 이상,01시,10\n"
        + "202201,남성,70대 이상,01시,5\n"
        + "202207,여성,20대,00시,7\n"
        + "202207,여성,20대,00시,3\n",
    )
    df = load_visitor_trend(path)
    assert df["visit_population_count"].tolist() == [15, 10]


# 문화축제 표준데이터


def test_festivals_header_row_and_jeju_filter(tmp_path, monkeypatch):
    calls = {}

    def fake_read_excel(path, header):
        calls["header"] = header
        return pd.DataFrame(
            {
                "축제명": ["제22회 쇠소깍축제", "2026 하영 빛나는 서귀포", "서울 축제"],
                "소재지도로명주소": ["제주특별자치도 서귀포시", None, "서울특별시"],
                "소재지지번주소": [None, None, None],
                "주최기관명": [None, "서귀포시", "서울시"],
                "주관기관명": [None, None, None],
            }
        )

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    df = load_festivals(tmp_path / "festivals.xls")
    assert calls["header"] == 1
    assert df["축제명"].tolist() == ["제22회 쇠소깍축제", "2026 하영 빛나는 서귀포"]
    assert df["is_duplicate"].tolist() == [False, True]
