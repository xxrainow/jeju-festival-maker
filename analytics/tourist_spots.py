"""관광지별 내국인 유입자 수의 관광지 → 읍면동 표.

관광지 자료에는 이름만 있어 위치를 따로 붙인다.
1) 공공와이파이 AP 정보에서 같은 이름(공백 무시) 또는 확인한 별칭의 AP 그룹 주소
2) AP에 없는 곳은 관광 안내 자료의 주소 (출처 링크 포함)
3) 여러 동에 걸친 곳(국립공원, 해양공원)은 제외

최종 동네(`admin_area`, 행정동·읍면)는 `fill_admin_areas`로 채운다.
읍면은 주소 그대로, 동 지역 AP 행은 AP 좌표 판정(`coord_admin_ref`), 좌표 없는 행은 법정동 변환표.
`confirmed`가 "확인"인 행만 집계에 쓴다.
초안 생성: uv run python -m analytics.tourist_spots [--overwrite]
최종 동네 채우기 (확인 표시 유지): uv run python -m analytics.tourist_spots --fill-admin
"""

import argparse
import re
from pathlib import Path

import pandas as pd

from analytics.area_link import area_level, build_lookup, load_bus_stations, load_wifi_ap
from analytics.boundary import load_jeju_boundaries
from analytics.dong_mapping import WEAK_EVIDENCE, build_pair_mapping, collect_pairs

TOURIST_SPOTS_PATH = Path("data/raw/jejuhub_tourist_spot_visitors.csv")
SPOT_AREAS_PATH = Path("analytics/reference/tourist_spot_areas.csv")

CONFIRMED = "확인"
NEEDS_CHECK = "확인 필요"
EXCLUDED = "제외"  # 위치를 정하지 못해 집계에서 뺌
METHOD_AP = "AP 이름 일치"
METHOD_AP_ALIAS = "AP 별칭"
METHOD_WEB = "관광 안내 자료"
METHOD_MULTI = "여러 동에 걸침"

# 관광지 자료 이름 → AP 그룹명 (이름이 달라 자동으로 맞지 않는 곳)
AP_ALIASES = {
    "감귤박물관": "서귀포감귤박물관",
    "도립미술관": "제주도립미술관",
    "만장굴관광지": "만장굴",
    "제주항일기념관": "항일기념관",
    "제주현대미술관": "현대미술관",
}

# 주소가 본관이 아닐 수 있어 이름에 키워드가 들어간 인근 AP 좌표로 판정하는 곳
NEARBY_AP_KEYWORDS = {"이중섭미술관": "이중섭"}
METHOD_NEARBY = "AP 좌표(인근)"
# fill_admin_areas가 계산하는 방법 (다시 채울 때 지우고 새로 계산). 지도 확인 등 직접 넣은 값은 유지
COMPUTED_METHODS = ("주소 읍면", "AP 좌표", "변환표")

MULTI_AREA_SPOTS = {
    "한라산국립공원": "제주시·서귀포시 여러 읍면동에 걸침",
    "마라해양도립공원": "마라도·가파도·송악산 일대 해역 (AP는 대정읍 상모리 한 곳)",
    "서귀포도립해양공원": "서귀포 앞바다와 섬 일대 해역",
}

# AP 정보에 없는 관광지: (주소, 시 읍면동, 출처, 비고)
WEB_ADDRESSES = {
    "국립제주박물관": (
        "제주시 일주동로 17 (건입동)",
        "제주시 건입동",
        "https://www.ktriptips.com/kor/culture/130461",
        "",
    ),
    "이중섭미술관": (
        "서귀포시 이중섭로 33 (지번 서귀동 514)",
        "서귀포시 서귀동",
        "https://www.ktriptips.com/kor/culture/130494",
        "",
    ),
    "제주목관아지": (
        "제주시 관덕로 25 (삼도이동)",
        "제주시 삼도이동",
        "https://www.ktriptips.com/kor/tourspot/128641",
        "",
    ),
    "제주도립 김창열미술관": (
        "제주시 한경면 저지리 (용금로 883-5)",
        "제주시 한경면",
        "https://m.go.seoul.co.kr/news/2016/09/20/20160920025049",
        "한경면 저지리 확인 (사용자 확인, 2026-11-04). 일부 자료는 한림읍으로 표기",
    ),
    "삼양선사유적지": (
        "제주시 선사로2길 13 (삼양일동)",
        "제주시 삼양일동",
        "https://www.ktriptips.com/kor/tourspot/129455",
        "",
    ),
    "중문대포해안주상절리대": (
        "서귀포시 이어도로 36-30 (중문동)",
        "서귀포시 중문동",
        "https://www.ktriptips.com/kor/tourspot/127053",
        "번지를 36-24로 적은 자료도 있음 (동은 같음)",
    ),
    "박물관은살아있다": (
        "서귀포시 중문관광로 42 (지번 색달동 2629)",
        "서귀포시 색달동",
        "카카오맵·네이버 지도 (사용자 확인, 2026-11-04)",
        "현재 이름이 K-아일랜드제주로 바뀐 것으로 보임 (자료 이름 유지)",
    ),
    "퍼시픽랜드": (
        "서귀포시 중문관광로 154-17 (지번 색달동 2950-17)",
        "서귀포시 색달동",
        "https://xn--ok0b236bp0a.com/place/11306",
        "",
    ),
    "한화아쿠아플라넷제주": (
        "서귀포시 성산읍 섭지코지로 95 (고성리)",
        "서귀포시 성산읍",
        "https://www.ktriptips.com/kor/culture/2048059",
        "",
    ),
}

COLUMNS = [
    "sight_name",
    "method",
    "matched_name",
    "address",
    "area",
    "area_level",
    "coord_admin_ref",
    "admin_area",
    "admin_method",
    "source",
    "note",
    "confirmed",
]


def _key(name: str) -> str:
    return re.sub(r"\s", "", name)


def build_draft(sight_names: list[str], ap: pd.DataFrame, boundaries=None) -> pd.DataFrame:
    """관광지 → 읍면동 초안. AP로 찾은 곳은 AP 좌표의 행정동을 참고값으로 붙인다."""
    lookup = build_lookup(ap, "place_key", "area").set_index("key")
    ap_keys = {_key(k): k for k in lookup.index}
    rows = []
    for name in sorted(sight_names):
        row = dict.fromkeys(COLUMNS, "")
        row.update(sight_name=name, confirmed=NEEDS_CHECK, area=None, area_level=None)
        target = AP_ALIASES.get(name, name)
        if name in MULTI_AREA_SPOTS:
            row.update(method=METHOD_MULTI, note=MULTI_AREA_SPOTS[name])
        elif _key(target) in ap_keys:
            key = ap_keys[_key(target)]
            found = lookup.loc[key]
            addresses = ap.loc[ap["place_key"] == key, "addressDong"].dropna().unique()
            row.update(
                method=METHOD_AP_ALIAS if name in AP_ALIASES else METHOD_AP,
                matched_name=key,
                address=" / ".join(sorted(addresses)),
                area=found["area"],
                area_level=area_level(found["area"], "법정동"),
                source="제주데이터허브 공공와이파이 AP 정보 (기준일 2022-12-25)",
            )
            if found["status"] != "연결":
                row["note"] = f"AP 주소가 여러 곳: {found['candidates']}"
            if boundaries is not None:
                points = ap.loc[ap["place_key"] == key, ["latitude", "longitude"]].dropna()
                admins = {boundaries.locate(lat, lon) for lat, lon in points.to_numpy()}
                row["coord_admin_ref"] = " / ".join(sorted(a for a in admins if a))
        elif name in WEB_ADDRESSES:
            address, area, source, note = WEB_ADDRESSES[name]
            row.update(
                method=METHOD_WEB,
                address=address,
                area=area,
                area_level=area_level(area, "법정동"),
                source=source,
                note=note,
            )
        else:
            row.update(method="못 찾음", note="AP와 관광 안내 자료에서 주소를 찾지 못함")
        rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)


def fill_admin_areas(df: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """비어 있는 `admin_area`를 채운다. 이미 채운 행(직접 확인한 곳 포함)은 건드리지 않는다."""
    df = df.copy()
    used = mapping[mapping["used"]].groupby("legal_dong")["admin_dong"].agg(list)
    weak = set(mapping.loc[mapping["evidence"].eq(WEAK_EVIDENCE), "legal_dong"])
    known = set(mapping["legal_dong"])
    for idx, row in df.iterrows():
        if isinstance(row["admin_area"], str) and row["admin_area"]:
            continue
        if row["method"] == METHOD_MULTI or not isinstance(row["area"], str):
            continue
        coord = row["coord_admin_ref"] if isinstance(row["coord_admin_ref"], str) else ""
        if row["area_level"] == "읍면":
            df.loc[idx, ["admin_area", "admin_method"]] = [row["area"], "주소 읍면"]
        elif coord:
            if " / " in coord:
                df.loc[idx, "admin_method"] = f"AP 좌표 여러 행정동: {coord}"
            else:
                df.loc[idx, ["admin_area", "admin_method"]] = [coord, "AP 좌표"]
        elif row["area"] in used:
            admins = used[row["area"]]
            if len(admins) == 1:
                method = f"변환표 ({WEAK_EVIDENCE})" if row["area"] in weak else "변환표"
                df.loc[idx, ["admin_area", "admin_method"]] = [admins[0], method]
            else:
                df.loc[idx, "admin_method"] = f"변환표 애매함: {' / '.join(sorted(admins))}"
        else:
            df.loc[idx, "admin_method"] = (
                "변환표 근거 부족" if row["area"] in known else "변환표 없음"
            )
    return df


def nearby_ap_admins(keyword: str, ap: pd.DataFrame, boundaries) -> tuple[list[str], list[str]]:
    """AP 그룹명에 keyword가 들어간 AP의 그룹명과, 좌표로 판정한 행정동 (경계 밖 제외)."""
    found = ap[ap["apGroupName"].str.contains(keyword, regex=False, na=False)]
    admins = {
        boundaries.locate(lat, lon) for lat, lon in zip(found["latitude"], found["longitude"])
    }
    return sorted(set(found["place_key"])), sorted(a for a in admins if a)


def apply_nearby_ap(df: pd.DataFrame, ap: pd.DataFrame, boundaries) -> pd.DataFrame:
    """`NEARBY_AP_KEYWORDS` 관광지: 인근 AP가 한 행정동이면 채우고 확인, 없거나 여러 동이면 제외."""
    df = df.copy()
    for name, keyword in NEARBY_AP_KEYWORDS.items():
        idx = df.index[df["sight_name"] == name]
        if idx.empty:
            continue
        places, admins = nearby_ap_admins(keyword, ap, boundaries)
        df.loc[idx, "matched_name"] = " / ".join(places)
        df.loc[idx, "coord_admin_ref"] = " / ".join(admins)
        df.loc[idx, "note"] = (
            f"주소가 본관이 아닐 수 있어 이름에 '{keyword}'가 들어간 인근 AP "
            f"({', '.join(places) or '없음'}) 좌표로 판정"
        )
        if len(admins) == 1:
            df.loc[idx, ["admin_area", "admin_method", "confirmed"]] = [
                admins[0],
                METHOD_NEARBY,
                CONFIRMED,
            ]
        else:
            reason = "인근 AP 없음" if not admins else "인근 AP가 여러 행정동"
            df.loc[idx, ["admin_area", "admin_method", "confirmed"]] = [None, reason, EXCLUDED]
    return df


def load_spot_table(path: Path = SPOT_AREAS_PATH) -> pd.DataFrame:
    """관광지 표 전체. `address_area`는 주소의 법정동·읍면 (`area` 열)."""
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    return df.rename(columns={"area": "address_area"})


def load_spot_areas(path: Path = SPOT_AREAS_PATH) -> pd.DataFrame:
    """확인된 관광지만 (`confirmed == "확인"`, 최종 동네 있음, 여러 동에 걸치지 않음)."""
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    usable = (
        df["confirmed"].eq(CONFIRMED) & df["admin_area"].notna() & df["method"].ne(METHOD_MULTI)
    )
    return df[usable].reset_index(drop=True)


def load_tourist_spot_visitors(path: Path = TOURIST_SPOTS_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"dtYearMonth": str, "sightsName": str}, encoding="utf-8-sig")
    df = df.rename(
        columns={
            "dtYearMonth": "base_year_month",
            "sightsName": "sight_name",
            "userCnt": "visitors",
        }
    )
    df["visitors"] = pd.to_numeric(df["visitors"])
    return df[["base_year_month", "sight_name", "visitors"]]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="관광지 → 읍면동 초안 생성")
    parser.add_argument("--overwrite", action="store_true", help="확인 표시가 있어도 덮어쓰기")
    parser.add_argument("--fill-admin", action="store_true", help="기존 표의 최종 동네만 채우기")
    args = parser.parse_args(argv)
    boundaries = load_jeju_boundaries()
    if args.fill_admin:
        ap = load_wifi_ap()
        mapping = build_pair_mapping(collect_pairs(ap, load_bus_stations(), boundaries))
        table = pd.read_csv(SPOT_AREAS_PATH, dtype=str, encoding="utf-8-sig")
        for col in COLUMNS:
            if col not in table:
                table[col] = None
        table = table[COLUMNS].copy()
        computed = table["admin_method"].fillna("").str.startswith(COMPUTED_METHODS)
        computed &= ~table["admin_method"].eq(METHOD_NEARBY)
        table.loc[computed, ["admin_area", "admin_method"]] = None
        table = fill_admin_areas(table, mapping)
        table = apply_nearby_ap(table, ap, boundaries)
        table.to_csv(SPOT_AREAS_PATH, index=False, encoding="utf-8-sig")
        print(table["admin_method"].fillna("-").value_counts().to_string())
        return
    if SPOT_AREAS_PATH.exists() and not args.overwrite:
        raise SystemExit(f"{SPOT_AREAS_PATH}가 이미 있습니다. 확인 표시를 지우려면 --overwrite")
    names = load_tourist_spot_visitors()["sight_name"].unique().tolist()
    draft = build_draft(names, load_wifi_ap(), boundaries)
    SPOT_AREAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    draft.to_csv(SPOT_AREAS_PATH, index=False, encoding="utf-8-sig")
    print(draft["method"].value_counts().to_string())


if __name__ == "__main__":
    main()
