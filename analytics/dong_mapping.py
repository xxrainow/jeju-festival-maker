"""법정동 → 행정동 변환표.

출처: 행정안전부_법정동별(행정동 통반단위) 성/연령별 주민등록 인구수 (공공데이터포털 15108074).
통·반 단위 인구를 (법정동, 행정동)으로 합쳐 변환표를 만든다.

- 법정동 하나가 행정동 하나에만 속하면 그대로 바꾼다
- 여러 행정동에 걸치면 기본은 애매함으로 두고 후보 행정동을 남긴다
- split=True이면 주민등록 인구 비율로 이용자 수를 나눈다 (`is_estimated=True`).
  거주 인구 비율이라 관광지·시장처럼 방문 장소의 실제 위치와 다를 수 있다
"""

import pandas as pd

from analytics.area_link import AMBIGUOUS, LINKED


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

    결과에 `conversion` 열을 붙인다: 1:1 변환, 여러 행정동, 인구 비율 분할, 변환표 없음.
    """
    df = linked.copy()
    df["conversion"] = None
    df["is_estimated"] = False
    target = df["status"].eq(LINKED) & df["area_level"].eq("법정동")

    admins = mapping.groupby("legal_dong")["admin_dong"].agg(list)
    candidates = df.loc[target, "area"].map(admins)

    missing = candidates.isna()
    df.loc[missing[missing].index, "conversion"] = "변환표 없음"

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
