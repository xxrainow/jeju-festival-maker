"""제주 소재 사전 (설계 기획서 6절, D 단계 산출물).

아이디어의 "재료" 축을 데이터로 만든다. 재료 1개당 1행.

만드는 방법 (기획서 6절 순서):
1. 후보 추출: 제주 축제명(문체부 3개년 + 전국문화축제표준데이터)에서 재료 단어를 찾는다.
   키워드 표는 research/reference/jeju_material_keywords.csv (축제명을 보고 사람이 정리, 팀이 고친다)
2. 장소 보강: 와이파이 장소명에 같은 키워드를 맞춰 관련 장소를 붙인다
3. 먹거리 보강(POS): 센터 데이터라 아직 없음
4. 관심 지표: 관련 장소의 관광 사용량 비중(와이파이, INTEREST_PERIOD)
5. 사람 검수: 키워드에 걸린 축제·장소 목록을 따로 저장한다 (REVIEW_PATH)

소재 강점 = (관광객 관심 지표 + 전국 희소성) / 2, 둘 다 0~1로 맞춘 값 (기획서 6절 "쓰이는 곳").

와이파이는 아이디어 단계(앞단)에만 쓰고 기간을 2023~2024로 둔다.
검증 단계(뒷단) 장소 확인은 2025년 자료를 써서 같은 숫자로 고르고 검증하지 않게 한다.

실행: uv run python -m research.materials
결과: data/processed/jeju_materials.csv, data/processed/jeju_material_review.csv
"""

import re
import sys
from pathlib import Path

import pandas as pd

from research.trends import load_panel, norm_name

KEYWORDS_PATH = Path(__file__).parent / "reference" / "jeju_material_keywords.csv"
MATERIALS_PATH = Path("data/processed/jeju_materials.csv")
REVIEW_PATH = Path("data/processed/jeju_material_review.csv")
STANDARD_FESTIVALS_PATH = Path("data/raw/전국문화축제표준데이터-20261103.xls")

INTEREST_PERIOD = ("202301", "202412")
NEUTRAL_INTEREST = 0.5
INTEREST_SOURCE = "와이파이 장소별 방문자별 사용량 2023-01~2024-12"
FESTIVAL_SOURCE = "제주 축제 (문체부 지역축제 2024-2026, 전국문화축제표준데이터)"
RARITY_SOURCE = "문체부 지역축제 2026 (제주 제외 전국)"

# 재료와 상관없는 시설 이름 (정류소, 충전소, 공공시설). 관광 비중을 흐리지 않게 뺀다
EXCLUDED_PLACE = re.compile(
    r"^(?:버스정류소|전기차충전소)|어린이 ?공원|어린이|보건소|주민센터|도서관|복지|학교|병원|청사"
    r"|사무소|마을회관|경로당|문화의집|노인|요양"
)


def load_keywords(path: Path = KEYWORDS_PATH) -> pd.DataFrame:
    kw = pd.read_csv(path, dtype=str, keep_default_na=False)
    kw["seasonal"] = kw["seasonal"].str.lower() == "true"
    kw["manual_months"] = kw["manual_months"].map(
        lambda s: tuple(int(m) for m in s.split("|")) if s else ()
    )
    for pattern in kw["keywords"]:
        re.compile(pattern)  # 잘못된 정규식은 여기서 바로 알린다
    return kw


def jeju_festivals(panel: pd.DataFrame, standard: pd.DataFrame | None) -> pd.DataFrame:
    """제주 축제 (축제명, 월, 출처). 같은 축제의 연도별 행은 (정규명, 월)로 한 번만 센다."""
    j = panel[panel["시도"] == "제주"][["축제명", "월"]].copy()
    j["출처"] = "문체부"
    frames = [j]
    if standard is not None and len(standard):
        s = standard[~standard.get("is_duplicate", False)].copy()
        s["월"] = pd.to_datetime(s["축제시작일자"], errors="coerce").dt.month
        s["출처"] = "표준데이터"
        frames.append(s[["축제명", "월", "출처"]])
    out = pd.concat(frames, ignore_index=True)
    out["축제명"] = out["축제명"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    out["_k"] = out["축제명"].map(norm_name)
    out = out.drop_duplicates(["_k", "월"]).drop(columns="_k")
    return out.reset_index(drop=True)


def wifi_place_shares(
    usage: pd.DataFrame, period: tuple[str, str] = INTEREST_PERIOD
) -> pd.DataFrame:
    """장소별 관광 사용량과 방문유형이 있는 전체 사용량. 사람 수가 아니라 데이터 사용량이다."""
    u = usage[
        usage["base_year_month"].between(*period)
        & usage["visit_type"].notna()
        & ~usage["wifi_place_name"].str.contains(EXCLUDED_PLACE)
    ]
    total = u.groupby("wifi_place_name")["use_amount"].sum()
    tour = u[u["visit_type"] == "관광"].groupby("wifi_place_name")["use_amount"].sum()
    out = pd.DataFrame({"total": total, "tourist": tour}).fillna(0)
    return out[out["total"] > 0]


def _months(row, months: list[int]) -> tuple[tuple[int, ...] | None, str]:
    if row["manual_months"]:
        return row["manual_months"], row["manual_months_basis"] or "수동 입력"
    if row["seasonal"] and months:
        return tuple(sorted(set(months))), "기존 제주 축제 개최 월"
    return None, "연중 (계절 제약 없음)"


def build_dictionary(
    panel: pd.DataFrame,
    standard: pd.DataFrame | None,
    places: pd.DataFrame | None,
    keywords: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(사전, 검수 목록). places는 wifi_place_shares 결과 (없으면 관심 지표를 비워 둔다)."""
    kw = load_keywords() if keywords is None else keywords
    fests = jeju_festivals(panel, standard)
    nation = panel[(panel["연도"] == panel["연도"].max()) & (panel["시도"] != "제주")]
    nation_names = nation["축제명"].astype(str)
    base_share = places["tourist"].sum() / places["total"].sum() if places is not None else None

    rows, review = [], []
    for _, r in kw.iterrows():
        pat = r["keywords"]
        hit = fests[fests["축제명"].str.contains(pat, regex=True)]
        months = hit["월"].dropna().astype(int).tolist()
        final_months, basis = _months(r, months)
        national_pct = float(nation_names.str.contains(pat, regex=True).mean() * 100)
        row = {
            "material": r["material"],
            "category": r["category"],
            "keywords": pat,
            "festival_count": len(hit),
            "festivals": "; ".join(hit["축제명"]),
            "festival_months": "|".join(str(m) for m in sorted(set(months))),
            "months": "|".join(str(m) for m in final_months) if final_months else "",
            "months_basis": basis,
            "national_share_pct": round(national_pct, 2),
            "place_count": 0,
            "places": "",
            "tourist_share_pct": None,
            "tourist_vs_avg": None,
        }
        review += [{"material": r["material"], "kind": "축제", "name": n} for n in hit["축제명"]]
        if places is not None:
            matched = places[places.index.to_series().str.contains(pat, regex=True)]
            row["place_count"] = len(matched)
            top = matched.sort_values("total", ascending=False).index[:10]
            row["places"] = "; ".join(top)
            if len(matched):
                share = matched["tourist"].sum() / matched["total"].sum()
                row["tourist_share_pct"] = round(share * 100, 2)
                row["tourist_vs_avg"] = round(share / base_share, 3) if base_share else None
            review += [
                {"material": r["material"], "kind": "와이파이 장소", "name": n}
                for n in matched.index
            ]
        rows.append(row)

    d = pd.DataFrame(rows)
    max_nat = d["national_share_pct"].max() or 1
    d["rarity"] = (1 - d["national_share_pct"] / max_nat).round(4)
    share = d["tourist_share_pct"]
    d["interest"] = (share / share.max()).round(4) if share.notna().any() else None
    # 관련 장소가 없어 관심 지표를 못 잰 재료는 중간값(NEUTRAL_INTEREST)으로 둔다.
    # 비워 두고 희소성만 쓰면 데이터가 없는 재료가 오히려 1등이 된다
    filled = d["interest"].fillna(NEUTRAL_INTEREST) if "interest" in d else NEUTRAL_INTEREST
    d["strength"] = ((filled + d["rarity"]) / 2).round(4)
    d["interest_status"] = d["tourist_share_pct"].notna().map({True: "ready", False: "pending"})
    d.attrs["base_tourist_share_pct"] = round(base_share * 100, 2) if base_share else None
    return d, pd.DataFrame(review)


def main(argv: list[str] | None = None) -> None:
    from analytics.loaders import load_festivals, load_wifi_usage

    argv = sys.argv[1:] if argv is None else argv
    panel = load_panel()
    standard = load_festivals(STANDARD_FESTIVALS_PATH) if STANDARD_FESTIVALS_PATH.exists() else None
    places = wifi_place_shares(load_wifi_usage())
    d, review = build_dictionary(panel, standard, places)
    MATERIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(MATERIALS_PATH, index=False, encoding="utf-8-sig")
    review.to_csv(REVIEW_PATH, index=False, encoding="utf-8-sig")
    cols = ["material", "category", "festival_count", "months", "place_count",
            "tourist_share_pct", "national_share_pct", "strength"]  # fmt: skip
    print(d[cols].sort_values("strength", ascending=False).to_string(index=False))
    print(f"전체 장소 관광 사용량 비중: {d.attrs['base_tourist_share_pct']}%")
    print(f"저장: {MATERIALS_PATH}, 검수 목록: {REVIEW_PATH}")


if __name__ == "__main__":
    main()
