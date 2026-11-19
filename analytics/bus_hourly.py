"""시간대별 버스 이용: 허브 "일별 시간대별 버스 승차 인원"(제주 전체)과 3-04 버스 정류소별 이용 현황.

허브 파일 (data/raw/일별시간대별버스승차인원수현황.csv, 실데이터)
- 제주 전체 합계라 정류소별 값이 없다. 시간대는 7개 묶음(01시-06시, 07시-09시, …, 22시-24시)
- 승차만 센다: 하루 합계가 정류소별 일별 이용(승하차 합계)의 약 49% (2023-12-25~2025-10-25 671일 중앙값)
- 쓰는 곳: 야간 귀가 참고 경고("제주 전체에서 22~24시 승차는 하루의 N%"), 3-04 가상 데이터의 시간대 비중

3-04 (센터 지정 데이터, 정류소 × 시간대 × 승하차유형 × 이용자구분)
- 실데이터(data/raw/에 "3-04" 또는 "정류소별 이용"이 든 CSV)가 없으면 가상 데이터(data/demo/)를 쓰고 is_synthetic=True
- event_hour_usage, night_return_usage가 정류소 승차 인원을 계산한다

요약표: uv run python -m analytics.real_checks --build → data/processed/bus_hourly_share.csv (reference에도 올림)
"""

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
HUB_HOURLY_PATH = RAW_DIR / "일별시간대별버스승차인원수현황.csv"
SHARE_PATH = Path("data/processed/bus_hourly_share.csv")
DEMO_DIR = Path("data/demo")
HUB_SOURCE = "제주데이터허브 일별 시간대별 버스 승차 인원"
STATION_SOURCE = "3-04 버스 정류소별 이용 현황"
REAL_KEYS = ("3-04", "정류소별 이용", "정류소별이용")
# 허브 시간대 묶음 → 시(0~23). 22시-24시의 24시는 0시로 본다
BANDS = {
    "01시-06시": [1, 2, 3, 4, 5, 6],
    "07시-09시": [7, 8, 9],
    "10시-12시": [10, 11, 12],
    "13시-15시": [13, 14, 15],
    "16시-18시": [16, 17, 18],
    "19시-21시": [19, 20, 21],
    "22시-24시": [22, 23, 0],
}
NIGHT_BAND = "22시-24시"
NIGHT_HOURS = (21, 22, 23)  # 야간 귀가 (3-04는 시 단위)
WEEKEND = ("토", "일")


def _nfc_find(keys, directory: Path | None = None) -> Path | None:
    directory = (
        RAW_DIR if directory is None else directory
    )  # 실행할 때의 RAW_DIR (테스트에서 바꿔 끼움)
    hits = sorted(
        p for p in directory.glob("*.csv*")
        if any(k in unicodedata.normalize("NFC", p.name) for k in keys)
    )  # fmt: skip
    return hits[-1] if hits else None


def load_hub_hourly(path: Path | None = None) -> pd.DataFrame:
    path = path or _nfc_find(("일별시간대별버스승차",)) or HUB_HOURLY_PATH
    df = pd.read_csv(path, dtype={"base_date": str}, encoding="utf-8-sig")
    unknown = set(df["base_hour"]) - set(BANDS)
    if unknown:
        raise ValueError(f"모르는 시간대 값: {sorted(unknown)}")
    if df.duplicated(["base_date", "base_hour", "user_type"]).any():
        raise ValueError("같은 날·시간대·이용자 유형 행이 겹쳐요")
    return df


def band_shares(hub: pd.DataFrame) -> pd.DataFrame:
    """평일·주말별 시간대 묶음 승차 비중과 하루 평균 승차, 이용자 유형 비중."""
    d = hub.assign(day_type=hub["day_of_week"].isin(WEEKEND).map({True: "주말", False: "평일"}))
    rows = []
    for day_type, g in [("전체", d), *d.groupby("day_type")]:
        total = g["user_count"].sum()
        days = g["base_date"].nunique()
        for band, v in g.groupby("base_hour")["user_count"].sum().items():
            rows.append({"day_type": day_type, "kind": "시간대", "key": band,
                         "share": v / total, "daily_mean": v / days})  # fmt: skip
        if day_type == "전체":
            for ut, v in g.groupby("user_type")["user_count"].sum().items():
                rows.append({"day_type": day_type, "kind": "이용자 유형", "key": ut,
                             "share": v / total, "daily_mean": v / days})  # fmt: skip
    out = pd.DataFrame(rows)
    first, last = hub["base_date"].min(), hub["base_date"].max()
    out["source"] = (
        f"{HUB_SOURCE} {first[:4]}-{first[4:6]}-{first[6:]}~{last[:4]}-{last[4:6]}-{last[6:]}"
    )
    return out


@lru_cache(maxsize=1)
def load_shares() -> pd.DataFrame | None:
    from analytics.reference_data import reference_first

    path = reference_first(SHARE_PATH.name, SHARE_PATH)
    return pd.read_csv(path, encoding="utf-8-sig") if path.exists() else None


def night_share_warning(shares: pd.DataFrame | None = None) -> str | None:
    """야간 귀가 참고 경고: 제주 전체 22~24시 승차 비중."""
    shares = load_shares() if shares is None else shares
    if shares is None:
        return None
    row = shares[(shares["day_type"] == "전체") & (shares["key"] == NIGHT_BAND)]
    if row.empty:
        return None
    return (
        f"참고: 제주 전체에서 22~24시 버스 승차는 하루의 {row['share'].iloc[0] * 100:.1f}%예요 "
        f"({row['source'].iloc[0]}). 밤 행사는 귀가 버스가 적을 수 있어요."
    )


# ---------- 3-04 정류소별 시간대 이용 ----------


@dataclass
class StationHourly:
    data: pd.DataFrame  # bus_station_id, base_date, hour, get_on_off_type, user_count
    is_synthetic: bool
    path: Path
    fallback_reason: str | None = None  # 센터 파일을 읽지 못해 가상 데이터로 대신한 이유

    @property
    def label(self) -> str:
        return STATION_SOURCE + (" (가상 데이터 2025-05-12~25)" if self.is_synthetic else "")


def find_station_hourly() -> tuple[Path, bool] | None:
    real = _nfc_find(REAL_KEYS)
    if real:
        return real, False
    demo = sorted(DEMO_DIR.glob("bus_station_hourly_demo_*.csv*"))
    return (demo[-1], True) if demo else None


@lru_cache(maxsize=1)
def load_station_hourly() -> StationHourly | None:
    found = find_station_hourly()
    if found is None:
        return None
    path, synthetic = found
    try:
        return _read_station_hourly(path, synthetic)
    except Exception as exc:  # noqa: BLE001 - 센터 파일 형식이 달라도 앱이 멈추지 않게
        if synthetic:
            return None
        from analytics.center_data import reason_text

        demo = sorted(DEMO_DIR.glob("bus_station_hourly_demo_*.csv*"))
        if not demo:
            return None
        data = _read_station_hourly(demo[-1], True)
        data.fallback_reason = reason_text(exc, "3-04 버스 정류소별 이용")
        return data


STATION_COLUMNS = ["base_date", "base_hour", "bus_station_id", "get_on_off_type", "user_count"]


def _read_station_hourly(path: Path, synthetic: bool) -> StationHourly:
    """UTF-8·CP949 모두 읽는다. 필수 열이 없으면 ValueError (이유는 화면 안내에 쓴다)."""
    from analytics.center_data import read_csv_any, require_columns

    df = read_csv_any(path, dtype={"bus_station_id": str, "base_date": str})
    require_columns(df, STATION_COLUMNS, "3-04 버스 정류소별 이용")
    df = df[STATION_COLUMNS].copy()
    df["hour"] = pd.to_numeric(df["base_hour"])
    return StationHourly(df.drop(columns="base_hour"), synthetic, path)


def boarding_by_hours(
    station_ids: list[str], hours, data: StationHourly | None = ...
) -> dict | None:
    """정류소들의 하루 평균 승차 인원 (hours 안)과 하루 승차 중 비중. 자료가 없으면 None."""
    data = load_station_hourly() if data is ... else data
    if data is None or not station_ids:
        return None
    d = data.data[data.data["bus_station_id"].isin([str(s) for s in station_ids])]
    d = d[d["get_on_off_type"] == "승차"]
    days = data.data["base_date"].nunique()
    if d.empty or not days:
        return {"stations": list(station_ids), "daily_boarding": 0.0, "share_pct": None,
                "hours": f"{min(hours)}~{max(hours)}시", "source": data.label,
                "is_synthetic": data.is_synthetic, "data_label": "가상 데이터" if data.is_synthetic else "실데이터"}  # fmt: skip
    in_hours = d[d["hour"].isin(list(hours))]["user_count"].sum()
    total = d["user_count"].sum()
    return {
        "stations": list(station_ids),
        "daily_boarding": round(in_hours / days, 1),
        "share_pct": round(in_hours / total * 100, 1) if total else None,
        "hours": f"{min(hours)}~{max(hours)}시",
        "source": data.label,
        "is_synthetic": data.is_synthetic,
        "data_label": "가상 데이터" if data.is_synthetic else "실데이터",
    }
