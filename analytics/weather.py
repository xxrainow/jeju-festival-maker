"""주별·월별 날씨 위험 표 (check_timing용).

출처: 기상청 기상자료개방포털 ASOS 일자료 (제주 184, 고산 185, 성산 188, 서귀포 189)
실행: uv run python -m analytics.weather
결과: data/processed/weather_weekly_risk.csv, weather_monthly_risk.csv, weather_station_by_dong.csv

- 기간은 2017~2025 9년. 원자료는 2016-10-01부터라 2016년은 쓰지 않는다
- 일강수량 빈칸은 0으로 본다 (무강수). 원자료에 0.0과 빈칸이 따로 있고, 0.0은 기상청 무강수일 기준에 해당한다.
  빈칸이 무강수라는 설명은 기상청 공식 문서에서 확인하지 못했다. 빈칸을 0으로 바꾼 행은 precip_blank로 표시한다
- 기온·풍속 빈칸은 결측으로 두고, 그 날은 해당 위험일 판정에서 뺀다 (개수는 따로 센다)
- 주차는 해마다 같은 날짜가 같은 주에 오도록 평년 기준 연중 날짜로 정한다 (2월 29일은 2월 28일과 같은 주)
- 동네 → 지점은 행정동 경계 중심에서 가장 가까운 지점. 지점 좌표는 analytics/reference/asos_stations_jeju.csv
"""

import math
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
OUTPUT_DIR = Path("data/processed")
STATIONS_PATH = Path("analytics/reference/asos_stations_jeju.csv")
SOURCE = "기상청 기상자료개방포털 ASOS 일자료"
STATIONS = {184: "제주", 185: "고산", 188: "성산", 189: "서귀포"}
FIRST_YEAR, LAST_YEAR = 2017, 2025
YEARS = LAST_YEAR - FIRST_YEAR + 1
COLUMNS = {
    "지점": "station_id",
    "지점명": "station",
    "일시": "date",
    "평균기온(°C)": "temp_mean",
    "최고기온(°C)": "temp_max",
    "일강수량(mm)": "precip_mm",
    "최대 풍속(m/s)": "wind_max",
}
RISKS = ["rainy", "heavy_rain", "strong_wind", "heat"]
RISK_LABELS = {
    "rainy": "비 오는 날",
    "heavy_rain": "폭우일",
    "strong_wind": "강풍일",
    "heat": "폭염일",
}


@dataclass(frozen=True)
class RiskThresholds:
    rainy_mm: float = 1.0  # 일강수량 이상
    heavy_rain_mm: float = 50.0  # 일강수량 이상
    strong_wind_ms: float = 14.0  # 최대풍속 이상 (강풍주의보 육상 풍속 기준과 같음)
    heat_c: float = 33.0  # 최고기온 이상


DEFAULT_THRESHOLDS = RiskThresholds()


def latest_asos_file(raw_dir: Path = RAW_DIR) -> Path:
    files = sorted(raw_dir.glob("OBS_ASOS_DD_*.csv"))
    if not files:
        raise FileNotFoundError("data/raw/에 OBS_ASOS_DD_*.csv가 없어요")
    return files[-1]


def load_asos_daily(path: Path | None = None) -> pd.DataFrame:
    """ASOS 일자료 (CP949). 2017~2025만 남기고, 지점 4곳의 날짜가 빠짐없는지 확인한다."""
    df = pd.read_csv(path or latest_asos_file(), encoding="cp949").rename(columns=COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"].dt.year.between(FIRST_YEAR, LAST_YEAR)].copy()
    missing_stations = set(STATIONS) - set(df["station_id"])
    if missing_stations:
        raise ValueError(f"지점이 빠졌어요: {sorted(missing_stations)}")
    expected = pd.date_range(f"{FIRST_YEAR}-01-01", f"{LAST_YEAR}-12-31")
    for sid, group in df.groupby("station_id"):
        gaps = expected.difference(group["date"])
        if len(gaps) or group["date"].duplicated().any():
            raise ValueError(f"{sid} 지점 날짜가 빠지거나 겹쳐요 (빠진 날 {len(gaps)}일)")
    df["precip_blank"] = df["precip_mm"].isna()
    df["precip_mm"] = df["precip_mm"].fillna(0.0)
    return df.reset_index(drop=True)


def mark_risk_days(df: pd.DataFrame, th: RiskThresholds = DEFAULT_THRESHOLDS) -> pd.DataFrame:
    """위험일 표시. 기온·풍속이 결측이면 그 위험일은 판정하지 않는다(NA)."""
    df = df.copy()
    df["rainy"] = df["precip_mm"] >= th.rainy_mm
    df["heavy_rain"] = df["precip_mm"] >= th.heavy_rain_mm
    df["strong_wind"] = (
        (df["wind_max"] >= th.strong_wind_ms).astype("boolean").mask(df["wind_max"].isna())
    )
    df["heat"] = (df["temp_max"] >= th.heat_c).astype("boolean").mask(df["temp_max"].isna())
    return df


def calendar_day(d: pd.Series) -> pd.Series:
    """평년(365일) 기준 연중 날짜. 2월 29일은 2월 28일로 본다."""
    month, day = d.dt.month, d.dt.day.where(~((d.dt.month == 2) & (d.dt.day == 29)), 28)
    return pd.Series(
        [date(2001, m, dd).timetuple().tm_yday for m, dd in zip(month, day)], index=d.index
    )


def week_of_year(d: pd.Series) -> pd.Series:
    """연중 주차 1~53. 53주는 12월 31일 하루."""
    return (calendar_day(d) - 1) // 7 + 1


def week_label(week: int) -> str:
    """주 시작일 기준 "8월 2주차"."""
    start = date(2001, 1, 1) + timedelta(days=(week - 1) * 7)
    return f"{start.month}월 {(start.day - 1) // 7 + 1}주차"


def _risk_table(df: pd.DataFrame, period: str) -> pd.DataFrame:
    df = df.assign(year=df["date"].dt.year)
    keys = ["station_id", "station", period]
    yearly = df.groupby([*keys, "year"])[RISKS].sum().reset_index()
    out = df.groupby(keys).agg(
        observed_days=("date", "size"),
        precip_blank_days=("precip_blank", "sum"),
        wind_missing_days=("wind_max", lambda s: s.isna().sum()),
        temp_max_missing_days=("temp_max", lambda s: s.isna().sum()),
    )
    for risk in RISKS:
        out[f"{risk}_days"] = yearly.groupby(keys)[risk].sum() / YEARS  # 9년 평균 (연평균 일수)
    for risk in ["heavy_rain", "strong_wind", "heat"]:
        out[f"{risk}_years"] = yearly.assign(hit=yearly[risk] > 0).groupby(keys)["hit"].sum()
    out["n_years"] = YEARS
    out["source"] = f"{SOURCE} {FIRST_YEAR}~{LAST_YEAR}"
    return out.reset_index()


def weekly_risk(df: pd.DataFrame) -> pd.DataFrame:
    """지점 × 연중 주차별 위험일 (9년 평균 일수, 9년 중 발생 연수)."""
    out = _risk_table(df.assign(week=week_of_year(df["date"])), "week")
    out.insert(3, "week_label", out["week"].map(week_label))
    out["summary"] = [
        f"{r.station}, {r.week_label}: {YEARS}년 중 {r.strong_wind_years}년 강풍, "
        f"{r.heavy_rain_years}년 폭우, 평균 비 오는 날 {r.rainy_days:.1f}일"
        for r in out.itertuples()
    ]
    return out


def monthly_risk(df: pd.DataFrame) -> pd.DataFrame:
    """지점 × 월별 위험일 (check_timing의 추천 월 단위)."""
    return _risk_table(df.assign(month=df["date"].dt.month), "month")


def load_station_coords(path: Path = STATIONS_PATH) -> pd.DataFrame | None:
    """지점 좌표 (station_id, station, latitude, longitude, source). 파일이 없으면 None."""
    return pd.read_csv(path, encoding="utf-8-sig") if path.exists() else None


def _km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def nearest_station_by_dong(boundaries, stations: pd.DataFrame) -> pd.DataFrame:
    """행정동 경계 중심(centroid)에서 가장 가까운 지점."""
    rows = []
    for area, geom in zip(boundaries.areas, boundaries.geoms):
        c = geom.centroid
        dist = {r.station: _km(c.y, c.x, r.latitude, r.longitude) for r in stations.itertuples()}
        best = min(dist, key=dist.get)
        rows.append(
            {
                "admin_area": area,
                "centroid_lat": c.y,
                "centroid_lon": c.x,
                "station": best,
                "distance_km": dist[best],
            }
        )
    return pd.DataFrame(rows).sort_values("admin_area").reset_index(drop=True)


def timing_weather_evidence(
    region: str | None,
    months: list[int],
    monthly: pd.DataFrame,
    station_by_dong: pd.DataFrame | None,
) -> tuple[dict, list[str], list[str]]:
    """check_timing evidence의 날씨 칸, sources, warnings.

    evidence: weather_station, strong_wind_days·heavy_rain_days·rainy_days·heat_days (추천 월을 합친
    연평균 일수, 9년 평균), weather_by_month (월별 일수와 9년 중 강풍·폭우가 있었던 해 수).
    계산할 수 없으면 값은 None이고 이유를 warnings에 적는다.
    """
    empty = {
        "weather_station": None,
        "strong_wind_days": None,
        "heavy_rain_days": None,
        "rainy_days": None,
        "heat_days": None,
        "weather_by_month": [],
    }
    sources = [f"{SOURCE} {FIRST_YEAR}~{LAST_YEAR}"]
    if not region:
        return empty, sources, ["지역이 없어 날씨 지점을 정하지 못했어요."]
    if station_by_dong is None:
        return empty, sources, ["지점 좌표가 없어 동네와 날씨 지점을 연결하지 못했어요."]
    match = station_by_dong.loc[station_by_dong["admin_area"] == region, "station"]
    if match.empty:
        return (
            empty,
            sources,
            [f"{region}은(는) 행정동 43개에 없는 이름이라 날씨 지점을 정하지 못했어요."],
        )
    station = match.iloc[0]
    rows = monthly[(monthly["station"] == station) & monthly["month"].isin(months)]
    by_month = [
        {
            "month": int(r.month),
            "strong_wind_days": round(r.strong_wind_days, 1),
            "strong_wind_years": int(r.strong_wind_years),
            "heavy_rain_days": round(r.heavy_rain_days, 1),
            "heavy_rain_years": int(r.heavy_rain_years),
            "rainy_days": round(r.rainy_days, 1),
            "heat_days": round(r.heat_days, 1),
        }
        for r in rows.sort_values("month").itertuples()
    ]
    evidence = {
        "weather_station": station,
        **{f"{k}_days": round(rows[f"{k}_days"].sum(), 1) for k in RISKS},
        "weather_by_month": by_month,
    }
    warnings = [
        f"날씨는 {station} 지점 {FIRST_YEAR}~{LAST_YEAR} {YEARS}년 평균이에요. 동네 안 날씨와 다를 수 있어요."
    ]
    if rows[["wind_missing_days", "temp_max_missing_days"]].to_numpy().sum():
        warnings.append("풍속·최고기온 결측일은 위험일 판정에서 뺐어요.")
    return evidence, sources, warnings


def main() -> None:
    from analytics.boundary import load_jeju_boundaries
    from analytics.report_area_link import table

    th = DEFAULT_THRESHOLDS
    df = mark_risk_days(load_asos_daily(), th)
    weekly, monthly = weekly_risk(df), monthly_risk(df)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    weekly.to_csv(OUTPUT_DIR / "weather_weekly_risk.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUTPUT_DIR / "weather_monthly_risk.csv", index=False, encoding="utf-8-sig")

    print(f"## {SOURCE} {FIRST_YEAR}~{LAST_YEAR} ({len(df):,}행, 기준 {asdict(th)})")
    summary = df.groupby("station").agg(
        precip_blank=("precip_blank", "sum"),
        wind_missing=("wind_max", lambda s: s.isna().sum()),
        temp_max_missing=("temp_max", lambda s: s.isna().sum()),
        annual_precip_mm=("precip_mm", lambda s: s.sum() / YEARS),
        **{f"{r}_per_year": (r, lambda s: s.sum() / YEARS) for r in RISKS},
    )
    print(table(summary.round(1).reset_index()))
    print("\n### 태풍 차바 2016-10-05 (분석 기간 밖, 기준 확인용)")
    raw = mark_risk_days(
        pd.read_csv(latest_asos_file(), encoding="cp949")
        .rename(columns=COLUMNS)
        .fillna({"precip_mm": 0.0}),
        th,
    )
    yes_no = {True: "예", False: "아니오"}
    chaba = raw[raw["date"] == "2016-10-05"]
    print(
        table(
            pd.DataFrame(
                {
                    "지점": chaba["station"],
                    "일강수량(mm)": chaba["precip_mm"],
                    "최대풍속(m/s)": chaba["wind_max"],
                    "폭우일": chaba["heavy_rain"].map(yes_no),
                    "강풍일": chaba["strong_wind"].map(yes_no),
                }
            )
        )
    )

    coords = load_station_coords()
    if coords is None:
        print(f"\n{STATIONS_PATH}가 없어 동네 → 지점 연결은 건너뛰었어요.")
        return
    by_dong = nearest_station_by_dong(load_jeju_boundaries(), coords)
    by_dong.to_csv(OUTPUT_DIR / "weather_station_by_dong.csv", index=False, encoding="utf-8-sig")
    print("\n### 동네 → 가장 가까운 지점")
    print(table(by_dong.groupby("station")["admin_area"].apply(", ".join).reset_index()))


if __name__ == "__main__":
    main()
