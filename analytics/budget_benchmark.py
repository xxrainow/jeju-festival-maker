"""문체부 유사 축제 예산 벤치마크 (설계 J단계 "규모·예산").

실행: uv run python -m analytics.budget_benchmark
결과 (data/processed/, 커밋 제외, 담당자 칸 없음):
- festival_plan_2026.parquet: 전체 축제와 품질 표시
- festival_budget_benchmark.csv: 축제 유형 × 장소 유형 × 기간별 예산 분포
- festival_plan_2026_jeju.csv: 제주 축제와 행정동 연결 결과

- 예산 단위는 백만원. 예산 결측, 장소 유형 "미정", 기간 미정은 벤치마크에서 뺀다
- 건수 5개 미만은 "표본 부족"
- 1인당 비용은 방문객을 "계측"한 축제만
"""

from pathlib import Path

import pandas as pd

from analytics.area_link import LINKED, NOT_FOUND, area_level
from analytics.dong_mapping import convert_legal_to_admin
from analytics.festival_plan import UNDECIDED_PLACE, assert_no_personal_info, load_festival_plan
from analytics.flow_spec import EMD_CODES
from analytics.report_area_link import table

OUTPUT_DIR = Path("data/processed")
MIN_SAMPLE = 5
GROUPS = ["festival_type", "place_type", "duration_class"]
GROUP_LABELS = {"festival_type": "축제 유형", "place_type": "장소 유형", "duration_class": "기간"}
JEJU = "제주"
MAPPING_PATH = OUTPUT_DIR / "legal_admin_mapping.csv"  # analytics.candidate_compare가 만든 변환표
MULTI_PLACE_WORDS = ("도내", "도 일원", "제주시 일원", "서귀포시 일원")


def eligible(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """벤치마크에 쓰는 행과 뺀 사유별 건수."""
    reasons = pd.Series(None, index=df.index, dtype="object")
    reasons[df["duration_class"].eq("미정")] = "기간 미정"
    reasons[df["place_type"].eq(UNDECIDED_PLACE)] = "장소 유형 미정"
    reasons[df["budget_total"].isna()] = "예산 결측"
    excluded = reasons.value_counts().rename_axis("뺀 사유").reset_index(name="건수")
    return df[reasons.isna()], excluded


def distribution(df: pd.DataFrame, by: list[str], value: str = "budget_total") -> pd.DataFrame:
    """그룹별 하위25%·중간값·상위25%와 건수. 5건 미만은 표본 부족."""
    out = (
        df.groupby(by, observed=True)[value]
        .agg(
            count="count",
            q25=lambda s: s.quantile(0.25),
            median="median",
            q75=lambda s: s.quantile(0.75),
        )
        .reset_index()
    )
    out["sample_note"] = out["count"].lt(MIN_SAMPLE).map({True: "표본 부족", False: ""})
    return out


def outlier_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """1인당 비용 극단값 축제를 넣었을 때와 뺐을 때의 중간값 비교 (축제 유형별)."""
    rows = []
    for name, group in [("전체", df), *df.groupby("festival_type")]:
        kept = group[~group["per_capita_outlier"]]
        rows.append(
            {
                "축제 유형": name,
                "예산 중간값 (포함)": group["budget_total"].median(),
                "예산 중간값 (제외)": kept["budget_total"].median(),
                "1인당 비용 건수 (포함)": group["per_capita_krw"].count(),
                "1인당 비용 중간값 (포함)": group["per_capita_krw"].median(),
                "1인당 비용 건수 (제외)": kept["per_capita_krw"].count(),
                "1인당 비용 중간값 (제외)": kept["per_capita_krw"].median(),
            }
        )
    return pd.DataFrame(rows)


def link_jeju(df: pd.DataFrame, mapping: pd.DataFrame | None) -> pd.DataFrame:
    """제주 축제의 개최 장소(시군구 + 읍면동 칸)를 행정동·읍면에 연결한다.

    1) 행정동 43개 이름과 같으면 연결 2) 그 밖의 동은 법정동으로 보고 변환표로 변환
    3) 읍면동이 "-"이면 장소명이 여러 곳(도내 일원 등)인지 표시하고 미연결로 둔다
    시군구와 장소명의 시가 다르면 `place_check`에 적는다.
    """
    jeju = df[df["sido"].eq(JEJU)].copy()
    emd = jeju["place_emd"].fillna("-")
    jeju["area"] = (jeju["place_sigungu"].fillna("") + " " + emd).where(emd.ne("-"))
    known = jeju["area"].isin(set(EMD_CODES.values()))
    jeju["area_level"] = [
        area_level(a, "행정동") if k else area_level(a, "법정동")
        for a, k in zip(jeju["area"], known)
    ]
    jeju["status"] = jeju["area"].notna().map({True: LINKED, False: NOT_FOUND})
    jeju["candidates"] = ""
    jeju["conversion"] = None
    if mapping is not None:
        jeju = convert_legal_to_admin(jeju, mapping)
    jeju["link_result"] = "행정동 이름 일치"
    jeju.loc[jeju["area_level"].eq("읍면"), "link_result"] = "읍면"
    converted = jeju["conversion"].notna()
    jeju.loc[converted, "link_result"] = "법정동 → " + jeju.loc[converted, "conversion"]
    multi = jeju["place_name"].fillna("").str.contains("|".join(MULTI_PLACE_WORDS))
    jeju.loc[emd.eq("-") & multi, "link_result"] = "여러 곳 (읍면동 없음)"
    jeju.loc[emd.eq("-") & ~multi, "link_result"] = "읍면동 없음"
    jeju = jeju.rename(columns={"area": "admin_area"})

    other_city = {"제주시": "서귀포", "서귀포시": "제주시"}
    jeju["place_check"] = [
        "시군구와 장소명의 시가 다름" if c in other_city and other_city[c] in str(n) else None
        for c, n in zip(jeju["place_sigungu"].fillna(""), jeju["place_name"])
    ]
    # 서홍동·중문동처럼 법정동 이름이기도 한 행정동: 조사표가 법정동을 뜻했다면 행정동이 다를 수 있다
    if mapping is not None:
        dual = jeju["link_result"].eq("행정동 이름 일치") & jeju["admin_area"].isin(
            set(mapping["legal_dong"])
        )
        jeju.loc[dual, "place_check"] = "법정동 이름이기도 함 (확인 필요)"
    return jeju.drop(columns=["status"])


def _labels(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(
        columns={
            **GROUP_LABELS,
            "count": "건수",
            "q25": "하위25%",
            "median": "중간값",
            "q75": "상위25%",
            "sample_note": "비고",
        }
    )


def main() -> None:
    df = load_festival_plan()
    assert_no_personal_info(df)
    bench_rows, excluded = eligible(df)
    bench = distribution(bench_rows, GROUPS)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_DIR / "festival_plan_2026.parquet", index=False)
    _labels(bench).to_csv(
        OUTPUT_DIR / "festival_budget_benchmark.csv", index=False, encoding="utf-8-sig"
    )
    mapping = pd.read_csv(MAPPING_PATH) if MAPPING_PATH.exists() else None
    jeju = link_jeju(df, mapping)
    assert_no_personal_info(jeju)
    jeju.to_csv(OUTPUT_DIR / "festival_plan_2026_jeju.csv", index=False, encoding="utf-8-sig")

    low, high = df.attrs["per_capita_bounds"]
    print(f"## 예산 벤치마크 (백만원, 전체 {len(df):,}건 중 {len(bench_rows):,}건 사용)")
    print(table(excluded))
    print(
        f"\n### 축제 유형 × 장소 유형 × 기간 ({len(bench)}칸, 표본 부족 {bench['sample_note'].ne('').sum()}칸)"
    )
    print(table(_labels(bench)))
    for col in GROUPS:
        print(f"\n### {GROUP_LABELS[col]}별")
        print(table(_labels(distribution(bench_rows, [col]))))

    print("\n## 품질 표시")
    print(
        table(
            df["visitor_method"]
            .value_counts(dropna=False)
            .rename_axis("계측 방법")
            .reset_index(name="건수")
        )
    )
    print(
        table(
            df["suspect_reasons"]
            .str.split(", ")
            .explode()
            .value_counts()
            .rename_axis("의심 사유")
            .reset_index(name="건수")
        )
    )
    print(f"\n1인당 비용 극단값 기준 (log10 IQR 1.5배): {low:,.0f}원 미만, {high:,.0f}원 초과")
    telecom = df["telecom_estimate"]
    usable = telecom & df["budget_total"].notna() & df["visitors"].gt(0)
    print(
        f"추정 중 계측 방법 비고가 '통신 데이터'인 축제: {telecom.sum()}건 (예산·방문객이 있어 1인당 비용 계산 가능 {usable.sum()}건)"
    )
    print("\n### 1인당 비용 극단값을 넣었을 때와 뺐을 때 (벤치마크 대상 행 기준)")
    print(table(outlier_comparison(bench_rows)))

    print(f"\n## 제주 축제 {len(jeju)}건의 행정동 연결")
    if mapping is None:
        print("변환표가 없어 법정동은 변환하지 않았어요 (analytics.candidate_compare 먼저 실행)")
    print(
        table(jeju["link_result"].value_counts().rename_axis("연결 결과").reset_index(name="건수"))
    )
    cols = ["name", "place_name", "place_sigungu", "place_emd", "link_result", "admin_area"]
    check = jeju[jeju["admin_area"].isna() | jeju["place_check"].notna()]
    out = check[[*cols, "place_check"]].astype("string").fillna("-")
    out.columns = ["축제명", "장소명", "시군구", "읍면동", "연결 결과", "행정동", "확인"]
    print(table(out))


if __name__ == "__main__":
    main()
