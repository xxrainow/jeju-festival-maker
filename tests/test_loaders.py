from datetime import date

import pandas as pd

from analytics.loaders import (
    aggregate_wifi_usage,
    find_abnormal_days,
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
    df = load_bus_usage(path).data
    assert set(df["station_name"]) == {
        "제주국제공항(대정,화순,일주서로)",
        "거슨새미오름,안돌오름",
        "한라병원",
    }
    assert df["user_count"].sum() == 104


# 2024-01의 월요일 5일. 29일만 중앙값(100)의 20% 미만
JANUARY_MONDAYS = (
    "20240101,한라병원,일반,100\n"
    "20240108,한라병원,일반,100\n"
    "20240115,한라병원,일반,90\n"
    "20240122,한라병원,일반,110\n"
    "20240129,한라병원,일반,19\n"
)


def test_find_abnormal_days_uses_same_month_weekday_median():
    daily = pd.DataFrame(
        {
            "base_date": pd.to_datetime(
                ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-02", "2024-02-05"]
            ),
            "total": [100, 100, 10, 5, 5],
        }
    )
    result = find_abnormal_days(daily, ratio=0.2)
    # 화요일(1/2)과 2월 월요일(2/5)은 각자 혼자라 중앙값이 자기 자신
    assert result["is_abnormal"].tolist() == [False, False, True, False, False]
    assert result["median"].tolist() == [100, 100, 100, 5, 5]
    assert result["sample_days"].tolist() == [3, 3, 3, 1, 1]


def test_bus_abnormal_days_are_excluded_by_default(tmp_path):
    path = write(tmp_path / "bus.csv", BUS_HEADER + JANUARY_MONDAYS)
    bus = load_bus_usage(path)
    assert bus.excluded_dates == [date(2024, 1, 29)]
    assert date(2024, 1, 29) not in set(bus.data["base_date"])
    assert bus.daily["is_abnormal"].sum() == 1


def test_bus_abnormal_days_can_be_kept(tmp_path):
    path = write(tmp_path / "bus.csv", BUS_HEADER + JANUARY_MONDAYS)
    bus = load_bus_usage(path, exclude_abnormal=False)
    assert bus.excluded_dates == []
    assert len(bus.data) == 5
    assert bus.daily["is_abnormal"].sum() == 1


def test_bus_abnormal_ratio_is_adjustable(tmp_path):
    path = write(tmp_path / "bus.csv", BUS_HEADER + JANUARY_MONDAYS)
    assert load_bus_usage(path, abnormal_ratio=0.1).excluded_dates == []


def test_bus_abnormal_days_judged_on_full_data(tmp_path):
    # 조회 기간을 좁혀도 중앙값은 전체 자료 기준
    path = write(tmp_path / "bus.csv", BUS_HEADER + JANUARY_MONDAYS)
    bus = load_bus_usage(path, start=date(2024, 1, 29), end=date(2024, 1, 29))
    assert bus.excluded_dates == [date(2024, 1, 29)]
    assert bus.data.empty


def test_bus_date_filter(tmp_path):
    path = write(
        tmp_path / "bus.csv",
        BUS_HEADER
        + "20240101,한라병원,일반,1\n20240102,한라병원,일반,2\n20240103,한라병원,일반,3\n",
    )
    bus = load_bus_usage(path, start=date(2024, 1, 2), end=date(2024, 1, 2))
    assert bus.data["user_count"].tolist() == [2]
    assert bus.daily["base_date"].tolist() == [date(2024, 1, 2)]


def test_bus_notes_list_missing_period_excluded_and_unstable_months(tmp_path):
    path = write(tmp_path / "bus.csv", BUS_HEADER + JANUARY_MONDAYS + "20240201,한라병원,일반,5\n")
    notes = " ".join(load_bus_usage(path).notes())
    assert "2022-08-12 ~ 2022-11-23" in notes
    assert "20% 미만인 날 1일 제외 (2024-01-29)" in notes
    assert "판정이 불안정함 (2024-02)" in notes


def test_bus_renamed_station_shares_key(tmp_path):
    path = write(
        tmp_path / "bus.csv",
        BUS_HEADER
        + "20241006,제주국제공항4(대정,화순,일주서로),일반,10\n"
        + "20241007,제주국제공항4(대정화순일주서로),일반,12\n",
    )
    df = load_bus_usage(path).data
    assert df["station_key"].nunique() == 1
    assert df["station_name"].nunique() == 2


def test_normalize_station_name():
    assert (
        normalize_station_name("제주국제공항 4 (대정, 화순·일주서로)")
        == "제주국제공항4(대정화순일주서로)"
    )


def test_bus_closed_station_is_kept(tmp_path):
    path = write(tmp_path / "bus.csv", BUS_HEADER + "20190101,(구)동홍동주민센터,경로,3\n")
    assert load_bus_usage(path).data["station_name"].tolist() == ["(구)동홍동주민센터"]


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


def test_bus_missing_period_note_only_when_range_overlaps(tmp_path):
    path = write(tmp_path / "bus.csv", BUS_HEADER + JANUARY_MONDAYS)
    outside = load_bus_usage(path, start=date(2023, 1, 1)).notes()
    assert not any("원자료 없음" in note for note in outside)
    inside = load_bus_usage(path, start=date(2022, 9, 1), end=date(2022, 10, 1)).notes()
    assert any("2022-08-12 ~ 2022-11-23 원자료 없음" in note for note in inside)
