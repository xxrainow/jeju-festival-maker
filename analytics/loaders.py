"""제주 공개 데이터 로더. 규칙 근거는 docs/data-check.md 참고."""

import re
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

RAW_DIR = Path("data/raw")
BUS_USAGE_PATH = RAW_DIR / "이용자유형별버스정류소이용인원현황.csv"
WIFI_USERS_PATH = RAW_DIR / "와이파이장소별사용자현황.csv"
WIFI_USAGE_PATH = RAW_DIR / "와이파이장소별방문자별사용량.csv"
VISITOR_TREND_PATH = RAW_DIR / "제주도방문내국인유동인구추이.csv"
FESTIVALS_PATH = RAW_DIR / "전국문화축제표준데이터-20261103.xls"

# 와이파이: 2020-09 이전은 집계 방식이 달라 쓰지 않는다
WIFI_START_MONTH = "202010"

# 버스: 데이터가 없는 기간과 하루 이용자가 비정상적으로 적은 날
BUS_MISSING_PERIOD = (date(2022, 8, 12), date(2022, 11, 23))
BUS_ABNORMAL_DATES = (
    date(2021, 12, 23),
    date(2022, 8, 11),
    date(2022, 11, 24),
    date(2022, 11, 25),
    date(2022, 11, 26),
    date(2022, 11, 27),
)

# 축제: 서귀포시가 등록한 축제를 제주특별자치도가 다시 등록한 행 (원자료를 직접 대조해 확인)
FESTIVAL_DUPLICATE_NAMES = frozenset(
    {
        "제30회 한라산청정고사리축제",
        "2026 하영 빛나는 서귀포",
        "2026 새연교 주말 문화공연 금토 새연쇼",
        "2026제주메밀축제 제주 메밀의 모든 것",
    }
)

_AP_NUMBER = re.compile(r"[\s_]*#\d+(?:-\d+)*$")
_STATION_PUNCT = re.compile(r"[\s,.·]")


def strip_ap_number(place_name: str) -> str:
    """장소명 끝의 AP 번호(`#1`, `#2-3`)를 지운다."""
    return _AP_NUMBER.sub("", place_name).strip()


def normalize_station_name(station_name: str) -> str:
    """시기별로 표기가 바뀐 정류소명을 잇기 위한 정규화 이름."""
    return _STATION_PUNCT.sub("", station_name)


def bus_exclusion_notes() -> list[str]:
    """분석 결과 warnings에 넣을 버스 데이터 제외 기간 설명."""
    start, end = BUS_MISSING_PERIOD
    abnormal = ", ".join(d.isoformat() for d in BUS_ABNORMAL_DATES)
    return [
        f"버스 이용 인원: {start.isoformat()} ~ {end.isoformat()} 원자료 없음",
        f"버스 이용 인원: 하루 이용자가 비정상적으로 적은 날 제외 ({abnormal})",
    ]


def load_bus_usage(
    path: Path = BUS_USAGE_PATH,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """버스 정류소 이용 인원.

    정류소명 안의 쉼표가 따옴표 없이 들어 있어 한 줄을 통째로 읽은 뒤
    첫 칸은 날짜, 마지막 두 칸은 유형·인원, 그 사이 전체를 정류소명으로 나눈다.
    """
    con = duckdb.connect()
    df = con.execute(
        r"""
        WITH parts AS (
            SELECT regexp_extract(line, '^(\d{8}),(.*),([^,]*),([^,]*)$',
                                  ['base_date', 'station_name', 'user_type', 'user_count']) AS r
            FROM read_csv($path, columns = {'line': 'VARCHAR'}, delim = '\x01', quote = '',
                          escape = '', header = true, auto_detect = false)
        ),
        bus AS (
            SELECT strptime(r.base_date, '%Y%m%d')::DATE AS base_date,
                   r.station_name AS station_name,
                   r.user_type AS user_type,
                   CAST(r.user_count AS BIGINT) AS user_count
            FROM parts
        )
        SELECT * FROM bus
        WHERE NOT list_contains($abnormal::DATE[], base_date)
          AND base_date >= coalesce($start::DATE, DATE '0001-01-01')
          AND base_date <= coalesce($end::DATE, DATE '9999-12-31')
        ORDER BY base_date, station_name, user_type
        """,
        {"path": str(path), "abnormal": list(BUS_ABNORMAL_DATES), "start": start, "end": end},
    ).df()
    con.close()

    df["base_date"] = df["base_date"].dt.date
    keys = {name: normalize_station_name(name) for name in df["station_name"].unique()}
    df["station_key"] = df["station_name"].map(keys)
    return df


def _load_wifi(path: Path, value_column: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df = df[df["base_year_month"] >= WIFI_START_MONTH].copy()
    df["wifi_place_name"] = df["wifi_place_name"].map(strip_ap_number)
    digits = df[value_column].str.replace(r"\D", "", regex=True)
    df[value_column] = pd.to_numeric(digits, errors="coerce").astype("Int64")
    return df.reset_index(drop=True)


def load_wifi_users(path: Path = WIFI_USERS_PATH) -> pd.DataFrame:
    """와이파이 장소별 사용자 수 (2020-10 이후)."""
    return _load_wifi(path, "user_count")


def load_wifi_usage(path: Path = WIFI_USAGE_PATH) -> pd.DataFrame:
    """와이파이 장소별 방문유형별 데이터 사용량 (2020-10 이후). 사람 수가 아니다."""
    df = _load_wifi(path, "use_amount")
    df["visit_type"] = df["visit_type"].replace({"NULL": pd.NA, "": pd.NA})
    return df


def aggregate_wifi_usage(df: pd.DataFrame) -> pd.DataFrame:
    """장소·월·방문유형별 사용량 합계. 방문유형 결측도 하나의 묶음으로 남긴다."""
    keys = ["wifi_place_name", "base_year_month", "visit_type"]
    return (
        df.groupby(keys, dropna=False, as_index=False)["use_amount"]
        .sum(min_count=1)
        .sort_values(keys, na_position="last")
        .reset_index(drop=True)
    )


def load_visitor_trend(path: Path = VISITOR_TREND_PATH) -> pd.DataFrame:
    """제주 방문 내국인 유동인구 추이 (제주 전체 합계).

    `24시`는 `00시`로 통일하고, 같은 칸이 여러 줄인 행은 합산한다.
    연도 간 비교는 하지 말고 같은 해 안의 비중으로만 쓴다.
    """
    df = pd.read_csv(path, dtype={"base_year_month": str}, encoding="utf-8-sig")
    df["time_range"] = df["time_range"].replace({"24시": "00시"})
    keys = ["base_year_month", "sex", "age_range", "time_range"]
    return df.groupby(keys, as_index=False)["visit_population_count"].sum()


def load_festivals(path: Path = FESTIVALS_PATH) -> pd.DataFrame:
    """전국 문화축제 표준데이터 중 제주 축제.

    1행이 비어 있어 2행을 헤더로 읽는다. 중복 등록된 행은 지우지 않고
    `is_duplicate`로 표시한다.
    """
    df = pd.read_excel(path, header=1)
    text_cols = ["소재지도로명주소", "소재지지번주소", "주최기관명", "주관기관명"]
    text = df[text_cols].fillna("").astype(str).agg(" ".join, axis=1)
    df = df[text.str.contains("제주|서귀포")].copy()
    df["is_duplicate"] = df["축제명"].isin(FESTIVAL_DUPLICATE_NAMES)
    return df.reset_index(drop=True)
