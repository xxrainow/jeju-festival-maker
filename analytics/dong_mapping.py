"""법정동 → 행정동 변환표.

기본 변환표 (`collect_pairs`, `build_pair_mapping`):
와이파이 AP·정류소의 법정동 주소와 좌표로 판정한 행정동의 짝을 모은다.
- 오류 의심 짝은 표에 남기되 변환 근거에서 뺀다: 짝 2개 이하, 다른 시, 동인데 읍면으로 판정
- 남은 행정동이 하나면 변환, 여럿이면 애매함 (실제로 여러 행정동에 걸친 법정동)

인구 비율 변환표 (`build_mapping`, 참고용, 현재 사용 안 함):
행정안전부_법정동별(행정동 통반단위) 성/연령별 주민등록 인구수 (공공데이터포털 15108074).
통·반 단위 인구를 (법정동, 행정동)으로 합쳐 변환표를 만든다.

- 법정동 하나가 행정동 하나에만 속하면 그대로 바꾼다
- 여러 행정동에 걸치면 기본은 애매함으로 두고 후보 행정동을 남긴다
- split=True이면 주민등록 인구 비율로 이용자 수를 나눈다 (`is_estimated=True`).
  거주 인구 비율이라 관광지·시장처럼 방문 장소의 실제 위치와 다를 수 있다
"""

import pandas as pd

from analytics.area_link import _LOT_NUMBER, AMBIGUOUS, LINKED, area_level, parse_area

MIN_PAIRS = 3
SUSPECT_FEW = f"짝 {MIN_PAIRS - 1}개 이하"
SUSPECT_CITY = "다른 시"
SUSPECT_EUPMYEON = "동인데 읍면으로 판정"
NO_EVIDENCE = "근거 부족"


def collect_pairs(ap: pd.DataFrame, stations: pd.DataFrame, boundaries) -> pd.DataFrame:
    """(법정동, 행정동) 짝. 법정동은 AP 주소와 정류소 지번 주소의 동, 행정동은 좌표 판정.

    열: legal_dong, admin_dong, place(AP 그룹명 또는 정류소명), source. 짝은 AP·정류소 한 대가 하나.
    """
    frames = []
    ap_legal = ap["area"].where(ap["area"].map(lambda a: area_level(a, "법정동")) == "법정동")
    frames.append(
        pd.DataFrame(
            {
                "legal_dong": ap_legal,
                "lat": ap["latitude"],
                "lon": ap["longitude"],
                "place": ap["place_key"],
                "source": "와이파이 AP",
            }
        )
    )
    address = stations["stationAddress"].fillna("")
    lot = address.str.contains(_LOT_NUMBER)
    st_legal = address[lot].map(parse_area)
    st_legal = st_legal.where(st_legal.map(lambda a: area_level(a, "법정동")) == "법정동")
    frames.append(
        pd.DataFrame(
            {
                "legal_dong": st_legal,
                "lat": stations.loc[lot, "latitude"],
                "lon": stations.loc[lot, "longitude"],
                "place": stations.loc[lot, "stationName"],
                "source": "버스 정류소",
            }
        )
    )
    df = pd.concat(frames, ignore_index=True).dropna(subset=["legal_dong"])
    df["admin_dong"] = [boundaries.locate(lat, lon) for lat, lon in zip(df["lat"], df["lon"])]
    df = df.dropna(subset=["admin_dong"])
    return df[["legal_dong", "admin_dong", "place", "source"]].reset_index(drop=True)


def _suspect_reason(legal: str, admin: str, pairs: int) -> str | None:
    reasons = []
    if legal.split()[0] != admin.split()[0]:
        reasons.append(SUSPECT_CITY)
    if area_level(admin, "행정동") == "읍면":
        reasons.append(SUSPECT_EUPMYEON)
    if pairs < MIN_PAIRS:
        reasons.append(SUSPECT_FEW)
    return ", ".join(reasons) or None


def build_pair_mapping(pairs: pd.DataFrame) -> pd.DataFrame:
    """짝으로 만든 변환표.

    열: legal_dong, admin_dong, pairs(이 행정동 짝 수), places(짝이 나온 장소 수, 참고),
    legal_pairs(법정동 전체 짝 수), share,
    suspect_reason(오류 의심 사유), used(변환 근거 여부), admin_count(근거로 남은 행정동 수)
    """
    m = (
        pairs.groupby(["legal_dong", "admin_dong"])
        .agg(pairs=("place", "size"), places=("place", "nunique"))
        .reset_index()
    )
    m["legal_pairs"] = m.groupby("legal_dong")["pairs"].transform("sum")
    m["share"] = m["pairs"] / m["legal_pairs"]
    m["suspect_reason"] = [
        _suspect_reason(lg, ad, n)
        for lg, ad, n in zip(m["legal_dong"], m["admin_dong"], m["pairs"])
    ]
    m["used"] = m["suspect_reason"].isna()
    m["admin_count"] = m.groupby("legal_dong")["used"].transform("sum")
    return m.sort_values(["legal_dong", "pairs"], ascending=[True, False]).reset_index(drop=True)


def build_mapping(population: pd.DataFrame) -> pd.DataFrame:
    """`legal_dong`, `admin_dong`, `population` 열(통·반 단위 가능)로 변환표를 만든다.

    법정동·행정동은 `시 동` 형식. 결과 열: legal_dong, admin_dong, population, weight, admin_count.
    """
    mapping = population.groupby(["legal_dong", "admin_dong"], as_index=False)["population"].sum()
    legal_total = mapping.groupby("legal_dong")["population"].transform("sum")
    mapping["weight"] = mapping["population"] / legal_total
    mapping["admin_count"] = mapping.groupby("legal_dong")["admin_dong"].transform("size")
    if (legal_total == 0).any():
        empty = sorted(mapping.loc[legal_total == 0, "legal_dong"].unique())
        raise ValueError(f"인구가 0인 법정동은 비율을 계산할 수 없습니다: {', '.join(empty)}")
    return mapping.sort_values(["legal_dong", "admin_dong"]).reset_index(drop=True)


def convert_legal_to_admin(
    linked: pd.DataFrame, mapping: pd.DataFrame, split: bool = False
) -> pd.DataFrame:
    """법정동으로 연결된 장소(`area_level == "법정동"`)를 행정동으로 바꾼다.

    결과에 `conversion` 열을 붙인다: 1:1 변환, 여러 행정동, 인구 비율 분할, 변환표 없음,
    근거 부족(짝 변환표에 있지만 짝이 모두 오류 의심).
    """
    df = linked.copy()
    df["conversion"] = None
    df["is_estimated"] = False
    target = df["status"].eq(LINKED) & df["area_level"].eq("법정동")

    known = set(mapping["legal_dong"])
    if "used" in mapping:  # 짝 변환표: 오류 의심 짝은 근거에서 뺀다
        mapping = mapping[mapping["used"]]
    admins = mapping.groupby("legal_dong")["admin_dong"].agg(list)
    candidates = df.loc[target, "area"].map(admins)

    missing = candidates.isna()
    no_evidence = df.loc[missing[missing].index, "area"].isin(known)
    df.loc[no_evidence.index, "conversion"] = "변환표 없음"
    df.loc[no_evidence[no_evidence].index, "conversion"] = NO_EVIDENCE

    single = candidates[~missing].map(len) == 1
    one = single[single].index
    df.loc[one, "area"] = candidates[one].str[0]
    df.loc[one, "area_level"] = "행정동"
    df.loc[one, "conversion"] = "1:1 변환"

    many = single[~single].index
    if not split:
        df.loc[many, "candidates"] = candidates[many].map(" / ".join)
        df.loc[many, "area"] = None
        df.loc[many, "area_level"] = None
        df.loc[many, "status"] = AMBIGUOUS
        df.loc[many, "conversion"] = "여러 행정동"
        return df

    rows = df.loc[many].merge(
        mapping[["legal_dong", "admin_dong", "weight"]], left_on="area", right_on="legal_dong"
    )
    rows["users"] = rows["users"] * rows["weight"]
    rows["area"] = rows["admin_dong"]
    rows["area_level"] = "행정동"
    rows["conversion"] = "인구 비율 분할"
    rows["is_estimated"] = True
    rows = rows.drop(columns=["legal_dong", "admin_dong", "weight"])
    out = pd.concat([df.drop(index=many), rows], ignore_index=True)

    # 분할 전후 이용자 합계 대조
    if abs(out["users"].sum() - df["users"].sum()) > 1e-6 * max(1, df["users"].sum()):
        raise ValueError("인구 비율 분할 전후 이용자 합계가 다릅니다")
    return out
