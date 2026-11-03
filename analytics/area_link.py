"""정류소·와이파이 장소를 읍면동에 연결한다.

허브 API 주소에서 읍·면 또는 동을 꺼내 붙인다.
- 버스 정류소 기본 정보의 `stationAddress`는 행정동 표기 (예: 일도2동)
- 공공와이파이 AP 정보의 `addressDong`은 법정동 표기 (예: 일도이동)
읍·면은 행정·법정 단위가 같다. 와이파이의 동 지역은 공식 법정동→행정동 매핑표를
확보한 뒤 변환한다.

연결 상태:
- 연결: 같은 이름(또는 ID)의 항목이 모두 같은 읍면동에 있음
- 애매함: 같은 이름인데 읍면동이 둘 이상. 추측해서 붙이지 않는다
- 주소 없음: 이름은 찾았지만 주소가 비었거나 시·읍면동을 읽을 수 없음
- 이름 없음: 기준 정보에서 이름을 찾지 못함
"""

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.loaders import normalize_station_name, strip_ap_number

RAW_DIR = Path("data/raw")
BUS_STATIONS_PATH = RAW_DIR / "jejuhub_bus_stations.csv"
WIFI_AP_PATH = RAW_DIR / "jejuhub_wifi_ap.csv"

LINKED, AMBIGUOUS, NO_ADDRESS, NOT_FOUND = "연결", "애매함", "주소 없음", "이름 없음"
STATUSES = [LINKED, AMBIGUOUS, NO_ADDRESS, NOT_FOUND]

_CITY = re.compile(r"(제주시|서귀포시)")
_EUPMYEON = re.compile(r"^\S+[읍면]$")
_DONG = re.compile(r"^\S+동$")
_LOT_NUMBER = re.compile(r"\s\d+(?:-\d+)?(?:번지)?$")
_STATION_ID = re.compile(r"[\[(](\d{9})[\])]")

_WIFI_CATEGORIES = [
    ("버스정류소", re.compile(r"버스정류소")),
    ("전기차충전소", re.compile(r"^전기차충전소")),
    ("공원", re.compile(r"공원$")),
    ("올레·코스", re.compile(r"^\d+(?:-\d+)?(?:-[A-Z])?코스(?:\(.*\))?$")),
]


def parse_area(address: str | None) -> str | None:
    """주소에서 `시 읍면` 또는 `시 동`을 꺼낸다. 리는 읍·면으로 묶는다."""
    if not isinstance(address, str):
        return None
    tokens = address.split()
    for i, token in enumerate(tokens):
        if _CITY.fullmatch(token) and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if _EUPMYEON.match(nxt) or _DONG.match(nxt):
                return f"{token} {nxt}"
    return None


def area_level(area: str | None, dong_level: str) -> str | None:
    """읍·면은 `읍면`, 동은 출처의 표기(`행정동`/`법정동`)."""
    if not isinstance(area, str):
        return None
    return "읍면" if _EUPMYEON.match(area.split()[-1]) else dong_level


def station_id_from_wifi_name(place_name: str) -> str | None:
    """`버스정류소_효돈초등학교_(효돈중학교방면)_[406000459]`의 정류소 ID. 여러 개면 마지막."""
    ids = _STATION_ID.findall(place_name)
    return ids[-1] if ids else None


def wifi_category(place_name: str) -> str:
    for category, pattern in _WIFI_CATEGORIES:
        if pattern.search(place_name):
            return category
    return "기타"


def build_lookup(df: pd.DataFrame, key_col: str, area_col: str) -> pd.DataFrame:
    """키별 읍면동 후보를 모아 상태를 정한다. 열: key, area, status, candidates."""
    rows = []
    for key, group in df.groupby(key_col, sort=True):
        areas = sorted(set(group[area_col].dropna()))
        if len(areas) == 1:
            rows.append((key, areas[0], LINKED, areas[0]))
        elif len(areas) > 1:
            rows.append((key, None, AMBIGUOUS, " / ".join(areas)))
        else:
            rows.append((key, None, NO_ADDRESS, ""))
    return pd.DataFrame(rows, columns=["key", "area", "status", "candidates"])


def load_bus_stations(path: Path = BUS_STATIONS_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    df["area"] = df["stationAddress"].map(parse_area)
    # 지번이 붙은 주소는 법정동 표기라 동 이름을 행정동으로 쓰지 않는다
    lot = df["stationAddress"].fillna("").str.contains(_LOT_NUMBER)
    df.loc[lot & (df["area"].map(lambda a: area_level(a, "동")) == "동"), "area"] = None
    df["station_key"] = df["stationName"].map(normalize_station_name)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    return df


def load_wifi_ap(path: Path = WIFI_AP_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    df["area"] = df["addressDong"].map(parse_area)
    df["place_key"] = df["apGroupName"].map(strip_ap_number)
    return df


def _apply_lookup(
    totals: pd.DataFrame, key_col: str, lookup: pd.DataFrame, method: str, dong_level: str
) -> pd.DataFrame:
    merged = totals.merge(lookup, how="left", left_on=key_col, right_on="key", validate="m:1")
    merged["method"] = np.where(merged["status"].notna(), method, None)
    merged["status"] = merged["status"].fillna(NOT_FOUND)
    merged["candidates"] = merged["candidates"].fillna("")
    merged["area_level"] = merged["area"].map(lambda a: area_level(a, dong_level))
    return merged.drop(columns="key")


def link_bus_usage(totals: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """정류소별 이용 인원(`station_key`, `users`)에 행정동·읍면을 붙인다."""
    lookup = build_lookup(stations, "station_key", "area")
    linked = _apply_lookup(totals, "station_key", lookup, "정류소명", "행정동")
    if len(linked) != len(totals):
        raise ValueError("정류소 연결 후 행 수가 달라졌습니다")
    return linked


def link_wifi_places(
    totals: pd.DataFrame, ap: pd.DataFrame, stations: pd.DataFrame
) -> pd.DataFrame:
    """와이파이 장소별 이용자(`wifi_place_name`, `users`)에 읍면동을 붙인다.

    1) AP 그룹명과 같은 이름(법정동) 2) 장소명 끝의 정류소 ID로 정류소 주소(행정동) 순서로 찾는다.
    """
    linked = _apply_lookup(
        totals, "wifi_place_name", build_lookup(ap, "place_key", "area"), "AP 그룹명", "법정동"
    )

    by_id = build_lookup(stations, "stationId", "area").set_index("key")
    ids = linked.loc[linked["status"] == NOT_FOUND, "wifi_place_name"].map(
        station_id_from_wifi_name
    )
    ids = ids[ids.isin(by_id.index)]
    matched = by_id.loc[ids]
    for col in ("area", "status", "candidates"):
        linked.loc[ids.index, col] = matched[col].to_numpy()
    linked.loc[ids.index, "method"] = "정류소 ID"
    linked.loc[ids.index, "area_level"] = [area_level(a, "행정동") for a in matched["area"]]

    linked["category"] = linked["wifi_place_name"].map(wifi_category)
    if len(linked) != len(totals):
        raise ValueError("와이파이 장소 연결 후 행 수가 달라졌습니다")
    return linked


def nearest_area_reference(linked: pd.DataFrame, stations: pd.DataFrame) -> pd.Series:
    """주소 없는 정류소의 좌표에서 가장 가까운 연결 정류소의 지역 (분포 확인용 참고값).

    연결 결과로 쓰지 않는다.
    """
    known = stations.dropna(subset=["area", "latitude", "longitude"])
    coords = (
        stations.dropna(subset=["latitude", "longitude"])
        .groupby("station_key")[["latitude", "longitude"]]
        .mean()
    )
    targets = linked.loc[linked["status"] == NO_ADDRESS, "station_key"]
    targets = targets[targets.isin(coords.index)]
    if targets.empty or known.empty:
        return pd.Series(dtype=object)
    point = coords.loc[targets].to_numpy()
    ref = known[["latitude", "longitude"]].to_numpy()
    nearest = ((point[:, None, :] - ref[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    return pd.Series(known["area"].to_numpy()[nearest], index=targets.index)


def match_summary(linked: pd.DataFrame) -> pd.DataFrame:
    """상태별 장소 수·이용자 수와 비율."""
    summary = (
        linked.groupby("status")
        .agg(places=("status", "size"), users=("users", "sum"))
        .reindex(STATUSES, fill_value=0)
    )
    summary["places_pct"] = summary["places"] / summary["places"].sum() * 100
    summary["users_pct"] = summary["users"] / summary["users"].sum() * 100
    return summary


def candidate_city(candidates: str) -> str:
    """후보 읍면동이 모두 같은 시이면 그 시, 아니면 `여러 시`, 후보가 없으면 `알 수 없음`."""
    cities = sorted({c.split()[0] for c in candidates.split(" / ") if c})
    if len(cities) == 1:
        return cities[0]
    return "여러 시" if cities else "알 수 없음"


# 동네별 집계에서 빼는 항목
EXCLUDE_OLLE = "올레 코스"
EXCLUDE_CROSS_CITY = "다른 시에 같은 이름의 정류소"


def mark_exclusions(linked: pd.DataFrame) -> pd.DataFrame:
    """동네별 집계에서 뺄 항목에 `excluded_reason`을 붙인다.

    - 올레 코스 (와이파이): 여러 동을 지나는 선형 경로라 한 동에 붙일 수 없다
    - 다른 시에 같은 이름의 정류소 (버스): 이용 자료에 이름만 있어 서로 다른 정류소를 나눌 수 없다
    """
    df = linked.copy()
    df["excluded_reason"] = None
    if "category" in df:
        df.loc[df["category"] == "올레·코스", "excluded_reason"] = EXCLUDE_OLLE
    if "station_key" in df:
        cross_city = df["status"].eq(AMBIGUOUS) & df["candidates"].map(candidate_city).eq("여러 시")
        df.loc[cross_city, "excluded_reason"] = EXCLUDE_CROSS_CITY
    return df


@dataclass(frozen=True)
class AreaGroup:
    """후보지로 쓰는 행정동 묶음. dongs는 `시 행정동` 또는 `시 읍면` 형식."""

    name: str
    dongs: frozenset[str]


def validate_groups(groups: list[AreaGroup]) -> None:
    seen: dict[str, str] = {}
    for group in groups:
        for dong in group.dongs:
            if dong in seen:
                raise ValueError(f"{dong}이(가) {seen[dong]}과 {group.name}에 모두 들어 있습니다")
            seen[dong] = group.name


def assign_groups(linked: pd.DataFrame, groups: list[AreaGroup]) -> pd.DataFrame:
    """행정동 단위로 연결된 장소에 후보지 묶음을 붙인다.

    - 연결된 장소: 행정동·읍면이 묶음 안에 있으면 그 묶음 (`동 연결`)
    - 애매한 장소: 후보 동이 모두 같은 묶음 안에 있으면 그 묶음 (`경계 묶음`). 상태는 애매함 그대로
    법정동으로만 연결된 장소는 행정동 변환 전까지 묶음에 넣지 않는다.
    """
    validate_groups(groups)
    owner = {dong: group.name for group in groups for dong in group.dongs}
    df = linked.copy()
    df["group"] = None
    df["group_method"] = None

    admin = df["status"].eq(LINKED) & df["area_level"].isin(["행정동", "읍면"])
    df.loc[admin, "group"] = df.loc[admin, "area"].map(owner)
    df.loc[admin & df["group"].notna(), "group_method"] = "동 연결"

    def boundary_group(candidates: str) -> str | None:
        names = {owner.get(c) for c in candidates.split(" / ")}
        return names.pop() if len(names) == 1 else None

    # 와이파이 애매함 후보는 법정동이라 행정동 묶음과 비교하지 않는다
    is_admin_source = df.get("method", pd.Series(index=df.index)).ne("AP 그룹명")
    ambiguous = df["status"].eq(AMBIGUOUS) & is_admin_source
    df.loc[ambiguous, "group"] = df.loc[ambiguous, "candidates"].map(boundary_group)
    df.loc[ambiguous & df["group"].notna(), "group_method"] = "경계 묶음"
    return df


def area_totals(linked: pd.DataFrame, by: str = "area") -> tuple[pd.DataFrame, pd.DataFrame]:
    """동네별(`area`) 또는 묶음별(`group`) 이용자 합계와 제외 요약.

    제외 항목(`excluded_reason`)은 합계에 넣지 않고 사유별 개수와 이용자 수만 돌려준다.
    """
    df = linked if "excluded_reason" in linked else mark_exclusions(linked)
    excluded = df["excluded_reason"].notna()
    summary = (
        df[excluded]
        .groupby("excluded_reason")
        .agg(places=("users", "size"), users=("users", "sum"))
        .reset_index()
    )
    kept = df[~excluded & df[by].notna()]
    if by == "area":
        kept = kept[kept["status"] == LINKED]
    totals = (
        kept.groupby(by)
        .agg(places=("users", "size"), users=("users", "sum"))
        .sort_values("users", ascending=False)
        .reset_index()
    )
    return totals, summary
