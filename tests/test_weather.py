import unicodedata
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
from shapely.geometry import box

from analytics.weather import (
    STATIONS,
    RiskThresholds,
    load_asos_daily,
    mark_risk_days,
    monthly_risk,
    nearest_station_by_dong,
    station_coords_from_meta,
    station_meta_files,
    timing_weather_evidence,
    week_label,
    week_of_year,
    weekly_risk,
)

HEADER = [
    "지점",
    "지점명",
    "일시",
    "평균기온(°C)",
    "최고기온(°C)",
    "일강수량(mm)",
    "최대 풍속(m/s)",
]


def asos_frame(start="2016-12-30", end="2025-12-31") -> pd.DataFrame:
    days = pd.date_range(start, end)
    rows = [
        (sid, name, d.strftime("%Y-%m-%d"), 15.0, 20.0, None, 5.0)
        for sid, name in STATIONS.items()
        for d in days
    ]
    return pd.DataFrame(rows, columns=HEADER)


def write(tmp_path, df) -> str:
    path = tmp_path / "OBS_ASOS_DD_test.csv"
    df.to_csv(path, index=False, encoding="cp949")
    return path


def set_day(df, station, day, **values):
    cols = {"temp_max": "최고기온(°C)", "precip": "일강수량(mm)", "wind": "최대 풍속(m/s)"}
    mask = (df["지점명"] == station) & (df["일시"] == day)
    for key, value in values.items():
        df.loc[mask, cols[key]] = value


def test_load_keeps_2017_2025_and_blank_precip_is_zero(tmp_path):
    raw = asos_frame()
    set_day(raw, "고산", "2017-03-01", wind=None)
    df = load_asos_daily(write(tmp_path, raw))
    assert df["date"].dt.year.min() == 2017
    assert len(df) == 4 * len(pd.date_range("2017-01-01", "2025-12-31"))
    assert (df["precip_mm"] == 0).all() and df["precip_blank"].all()
    assert df["wind_max"].isna().sum() == 1  # 풍속 빈칸은 결측 그대로


def test_load_rejects_missing_station_or_dates(tmp_path):
    raw = asos_frame()
    with pytest.raises(ValueError, match="지점"):
        load_asos_daily(write(tmp_path, raw[raw["지점"] != 188]))
    with pytest.raises(ValueError, match="빠진 날 1일"):
        load_asos_daily(write(tmp_path, raw[raw["일시"] != "2020-02-29"]))


def test_thresholds_and_missing_values():
    df = pd.DataFrame(
        {
            "precip_mm": [0.9, 1.0, 50.0, 0.0],
            "wind_max": [13.9, 14.0, None, 0.0],
            "temp_max": [32.9, 33.0, 20.0, None],
        }
    )
    out = mark_risk_days(df)
    assert out["rainy"].tolist() == [False, True, True, False]
    assert out["heavy_rain"].tolist() == [False, False, True, False]
    assert out["strong_wind"].tolist()[:2] == [False, True] and pd.isna(out["strong_wind"][2])
    assert out["heat"].tolist()[:2] == [False, True] and pd.isna(out["heat"][3])
    custom = mark_risk_days(df, RiskThresholds(strong_wind_ms=10.0, rainy_mm=0.5))
    assert custom["strong_wind"].iloc[0] and custom["rainy"].iloc[0]


def test_week_of_year_same_dates_every_year():
    d = pd.Series(pd.to_datetime(["2023-01-01", "2023-01-07", "2023-01-08", "2023-12-31"]))
    assert week_of_year(d).tolist() == [1, 1, 2, 53]
    leap = pd.Series(pd.to_datetime(["2024-02-28", "2024-02-29", "2024-03-01", "2023-03-01"]))
    weeks = week_of_year(leap).tolist()
    assert weeks[0] == weeks[1] and weeks[2] == weeks[3]
    assert week_label(32) == "8월 1주차"  # 32주는 8월 6일 시작
    assert week_label(1) == "1월 1주차"


def test_weekly_and_monthly_risk_counts_over_nine_years(tmp_path):
    raw = asos_frame()
    for year in [2018, 2020, 2022, 2024]:  # 9년 중 4년, 고산 8월 10일 강풍
        set_day(raw, "고산", f"{year}-08-10", wind=20.0)
    for year in range(2017, 2026):  # 매년 8월 11일 비
        set_day(raw, "고산", f"{year}-08-11", precip=12.0)
    df = mark_risk_days(load_asos_daily(write(tmp_path, raw)))
    weekly = weekly_risk(df)
    week = week_of_year(pd.Series(pd.to_datetime(["2023-08-10"])))[0]
    row = weekly[(weekly["station"] == "고산") & (weekly["week"] == week)].iloc[0]
    assert row["strong_wind_years"] == 4
    assert row["strong_wind_days"] == pytest.approx(4 / 9)
    assert row["rainy_days"] == pytest.approx(1.0)
    assert row["strong_wind_above_avg"] and row["worse_than_usual"] == "비·바람"
    assert row["summary"].startswith(f"고산, {row['week_label']}: 평소보다 비·바람 많음")
    assert "참고: 14m/s 이상 강풍 9년 중 4년" in row["summary"]
    month = monthly_risk(df).set_index(["station", "month"]).loc[("고산", 8)]
    assert month["strong_wind_years"] == 4 and month["observed_days"] == 31 * 9


FAKE_BOUNDARIES = SimpleNamespace(
    areas=["제주시 한경면", "서귀포시 성산읍"],
    geoms=[box(126.15, 33.25, 126.25, 33.35), box(126.85, 33.40, 126.95, 33.50)],
)


def test_nearest_station_by_dong():
    stations = pd.DataFrame(
        {
            "station": ["고산", "성산"],
            "latitude": [33.30, 33.40],
            "longitude": [126.20, 126.90],
        }
    )
    out = nearest_station_by_dong(FAKE_BOUNDARIES, stations).set_index("admin_area")
    assert out.loc["제주시 한경면", "station"] == "고산"
    assert out.loc["서귀포시 성산읍", "station"] == "성산"
    assert out.loc["제주시 한경면", "distance_km"] < 1


def windy_january_rainy_august(tmp_path) -> pd.DataFrame:
    raw = asos_frame()
    for year in range(2017, 2026):
        set_day(raw, "고산", f"{year}-01-10", wind=20.0)
        set_day(raw, "고산", f"{year}-08-11", precip=12.0)
    return monthly_risk(mark_risk_days(load_asos_daily(write(tmp_path, raw))))


def test_relative_ratio_compares_within_station(tmp_path):
    monthly = windy_january_rainy_august(tmp_path).set_index(["station", "month"])
    # 고산 강풍은 1월에만: 1월 비율 ÷ 고산 연평균 비율 = (9/279) ÷ (9/3287)
    assert monthly.loc[("고산", 1), "strong_wind_ratio"] == pytest.approx(3287 / 279)
    assert monthly.loc[("고산", 1), "strong_wind_above_avg"]
    assert monthly.loc[("고산", 8), "strong_wind_ratio"] == 0
    assert not monthly.loc[("고산", 8), "strong_wind_above_avg"]
    # 강풍이 한 번도 없는 지점은 배수를 계산하지 않고 나쁘다고 보지 않음
    assert pd.isna(monthly.loc[("제주", 1), "strong_wind_ratio"])
    assert not monthly.loc[("제주", 1), "strong_wind_above_avg"]


def test_timing_weather_evidence(tmp_path):
    monthly = windy_january_rainy_august(tmp_path)
    by_dong = pd.DataFrame({"admin_area": ["제주시 한경면"], "station": ["고산"]})
    evidence, sources, warnings = timing_weather_evidence("제주시 한경면", [8, 9], monthly, by_dong)
    assert evidence["weather_station"] == "고산"
    assert evidence["worse_than_usual"] == ["비"]
    assert evidence["relative_to_station"]["strong_wind"] == 0
    assert evidence["rainy_days"] == 1.0 and evidence["strong_wind_days"] == 0
    assert [m["month"] for m in evidence["weather_by_month"]] == [8, 9]
    assert evidence["weather_by_month"][0]["worse_than_usual"] == ["비"]
    assert sources == ["기상청 기상자료개방포털 ASOS 일자료 2017~2025"]
    assert "9년 평균" in warnings[0] and len(warnings) == 1  # 강풍 없으면 참고 경고 없음

    evidence, _, warnings = timing_weather_evidence("제주시 한경면", [1], monthly, by_dong)
    assert evidence["worse_than_usual"] == ["바람"]
    assert any("14m/s 이상 강풍일이 연평균 1.0일" in w for w in warnings)

    for region, mapping, text in [
        (None, by_dong, "지역이 없어"),
        ("제주시 한경면", None, "지점 좌표가 없어"),
        ("제주시 없는동", by_dong, "43개에 없는"),
    ]:
        evidence, _, warnings = timing_weather_evidence(region, [8], monthly, mapping)
        assert evidence["strong_wind_days"] is None and evidence["worse_than_usual"] is None
        assert text in warnings[0]


def test_station_coords_from_meta_uses_current_rows(tmp_path):
    rows = [
        (184, "1923-05-01", None, "제주", 33.5141, 126.5297),
        (185, "1988-01-01", None, "고산", 33.2938, 126.1628),
        (188, "2008-09-04", None, "성산", 33.3868, 126.8802),
        (188, "1971-07-15", "2008-09-04", "성산", 33.3868, 126.8804),
        (189, "2010-11-09", None, "서귀포", 33.2462, 126.5653),
        (90, "1968-01-01", None, "속초", 38.25, 128.56),
    ]
    meta = pd.DataFrame(rows, columns=["지점", "시작일", "종료일", "지점명", "위도", "경도"])
    meta["지점주소"] = "주소"
    name = unicodedata.normalize("NFD", "META_관측지점정보_test.csv")  # 맥에서 받은 파일 이름
    meta.to_csv(tmp_path / name, index=False, encoding="cp949")
    files = station_meta_files(tmp_path)
    assert len(files) == 1
    coords = station_coords_from_meta(files[0])
    assert coords["station_id"].tolist() == [184, 185, 188, 189]
    assert coords.set_index("station").loc["성산", "longitude"] == 126.8802  # 현재 위치
    assert coords["source"].str.startswith("기상청 기상자료개방포털 관측지점정보").all()
    with pytest.raises(ValueError, match="현재 위치"):
        meta[meta["지점"] != 189].to_csv(tmp_path / name, index=False, encoding="cp949")
        station_coords_from_meta(files[0])


def test_week_label_dates_are_calendar_based():
    assert date(2001, 8, 6).timetuple().tm_yday == (32 - 1) * 7 + 1
