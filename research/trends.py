"""문체부 '지역축제 개최계획' 3개년(2024~2026) 표준화, 축제 단위 연결, 소재·포맷 트렌드.

설계 기획서 3절(트렌드 판정 방법)의 구현이다. 레포 밖 분석 파일(trend_pipeline.py)을 옮겼고,
결과 숫자가 같게 나오는지 tests/test_trends.py와 `축제트렌드_분석결과_2024-2026.xlsx`로 확인했다.

- 트렌드는 방문객이 아니라 공급 신호(새로 생기는 축제가 어느 소재로 몰리나)로 판정한다
- 방문객 성장률은 지자체 자체 보고라 참고값으로만 남긴다 (CLAUDE.md 3절)
- 예산 단위는 원자료 그대로 백만 원이다. 원으로 바꿀 때는 `BUDGET_UNIT_KRW`를 곱한다

원자료 → 패널 저장 (최초 1회):
    uv run python -m research.trends
원자료 위치: data/raw/mcst/mcst_2024.xlsx, mcst_2025.xlsx, mcst_2026.xlsx (Git 제외)
"""

import difflib
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAW_DIR = Path("data/raw/mcst")
PANEL_PATH = Path("data/processed/festival_panel_2024_2026.parquet")
YEARS = (2024, 2025, 2026)
SOURCE = "문체부 지역축제 개최계획 2024-2026"
BUDGET_UNIT_KRW = 1_000_000  # 원자료 예산 단위: 백만 원

TYPE_MAP = {
    "문화예술": "문화예술", "문화·예술": "문화예술", "자연생태": "자연생태", "전통역사": "전통역사",
    "주민화합": "주민화합", "기타(주민화합)": "주민화합", "지역특산물": "지역특산물", "특산물": "지역특산물",
}  # fmt: skip

_TYPE_KEYWORDS = [
    ("문화예술", r"문화예술|예술|문화관광|과학"),
    ("지역특산물", r"특산|수산물|먹거리|음식|농특산"),
    ("자연생태", r"생태|자연|꽃"),
    ("전통역사", r"전통|역사|역시"),
    ("주민화합", r"주민|화합|화홥|기타|체험|관광|상권|시장|산업|경제|테마|놀이|체육|안전|지역"),
]

# 소재·포맷 태그 (축제명 기반; 2026년 신설 vs 기존 n-gram 리프트 분석으로 도출)
TAGS = {
    "크리스마스·연말": r"크리스마스|산타|연말|성탄|윈터원더",
    "야간·빛·드론": r"야간|야행|한밤|유등|여름밤|밤하늘|빛|라이트|불빛|드론|미디어아트|조명|불꽃|별빛|달빛",
    "여름·물놀이": r"여름|썸머|서머|워터|물놀이|물총",
    "도심·거리·골목": r"도심|거리|골목|원도심|로드|스트리트",
    "시장·상권": r"시장|상점가|상권|야시장|마켓|장터",
    "정원·가드닝": r"정원|가드닝|가든|플라워쇼",
    "맥주·주류": r"맥주|치맥|비어|와인|막걸리|하이볼|전통주|술축제|양조",
    "푸드·디저트": r"푸드|빵|디저트|커피|떡볶이|치킨|치맥|김치|장류|미식|먹거리|맛|국수|김밥|라면",
    "봄꽃": r"봄꽃|벚꽃|유채|매화|튤립|진달래|산수유|복사꽃|청보리|철쭉",
    "가을꽃·단풍": r"국화|코스모스|억새|단풍|구절초|핑크뮬리",
    "농축산 특산": (
        r"사과|한우|복숭아|인삼|딸기|고추|마늘|감자|포도|수박|버섯|쌀|한돈|흑돼지|도새기|고사리"
        r"|감귤|녹차|메밀|토마토|블루베리|밤축제|한라봉"
    ),
    "수산물": (
        r"수산|대게|굴|전어|멸치|새우|방어|고등어|오징어|장어|해산물|꼬막|주꾸미|숭어|자리돔"
        r"|부시리|갈치|광어|소라|조개|전복|도다리|가리비|우럭|김장|해산"
    ),
    "문화제·예술제": r"문화제|예술제",
    "국제·박람회": r"국제|박람회|엑스포|EXPO",
    "음악·공연": r"음악|뮤직|재즈|(?<!바지)락|록페|콘서트|가요|K-?POP|버스킹",
    "영화·책·아트": r"영화|아트|미술|(?<!정)책|북페스티벌|북축제|문학|사진",
    "겨울 레저": r"겨울|눈꽃|얼음|빙어|송어|산천어|썰매",
    "걷기·러닝·스포츠": r"걷기|러닝|마라톤|트레킹|자전거|레이스|런닝",
}

VERDICT_ORDER = {"확실한 상승": 0, "관찰 대상(신설 적음)": 1, "정체": 2, "성숙·감소": 3}


# ---------- 원자료 표준화 ----------


def _strip_code(s: pd.Series) -> pd.Series:
    """'1. 서울'처럼 앞에 붙은 번호를 지운다."""
    return s.astype(str).str.replace(r"^\s*\d+\.\s*", "", regex=True).str.strip()


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.strip(), errors="coerce")


def _nan_text_to_na(s: pd.Series) -> pd.Series:
    return s.where(s != "nan")


def _map_type(value) -> str:
    x = re.sub(r"^\s*\d+\.\s*", "", str(value)).replace(" ", "")
    if x in TYPE_MAP:
        return TYPE_MAP[x]
    hits = [(m.start(), t) for t, p in _TYPE_KEYWORDS if (m := re.search(p, x))]
    return min(hits)[1] if hits else "주민화합"  # 2025~ 설문에는 '기타'가 없고 5개 유형뿐


def norm_name(name) -> str:
    """연도·회차·괄호·기호와 끝의 '축제' 같은 말을 지워 연도끼리 같은 축제를 찾는 키로 쓴다."""
    n = str(name)
    n = re.sub(r"\(.*?\)|\[.*?\]|「.*?」|<.*?>", "", n)
    n = re.sub(r"제\s*\d+\s*회", "", n)
    n = re.sub(r"20\d\d\s*년?", "", n)
    n = re.sub(r"[^0-9A-Za-z가-힣]", "", n)
    n = re.sub(r"(축제|페스티벌|페스타|festival)$", "", n, flags=re.IGNORECASE)
    return n


def load_mcst(path: Path, year: int, engine: str = "calamine") -> pd.DataFrame:
    """연도마다 다른 엑셀 양식을 같은 칸 구성으로 읽는다."""
    if year == 2024:
        raw = pd.read_excel(path, sheet_name="세부현황", engine=engine, header=None).iloc[6:]
        d = pd.DataFrame({
            "연번": raw[1], "시도": raw[2], "기초": raw[3], "축제명": raw[4], "유형_raw": raw[5],
            "기간_raw": raw[6], "장소명": raw[7], "장소유형": np.nan, "최초개최연도": raw[9],
            "예산": raw[10], "방문객": raw[14], "방문객_내": raw[15], "방문객_외": raw[16],
            "개최주기": np.nan,
        })  # fmt: skip
        month = d["기간_raw"].astype(str).str.extract(r"(\d{1,2})\s*[.월]")[0]
        d["월"] = _num(month)
    elif year in (2025, 2026):
        raw = pd.read_excel(path, sheet_name="조사표", engine=engine, header=None)
        raw = raw.iloc[7:] if year == 2025 else raw.iloc[8:]
        if year == 2025:
            c = {"주기": 19, "최초": 21, "예산": 22, "방": 26, "내": 27, "외": 28}
        else:
            c = {"주기": 19, "최초": 20, "예산": 21, "방": 26, "내": 27, "외": 28}
        d = pd.DataFrame({
            "연번": raw[1], "시도": raw[2], "기초": raw[3], "축제명": raw[4], "유형_raw": raw[5],
            "장소명": raw[6], "장소유형": raw[7], "월": _num(raw[12]),
            "개최주기": raw[c["주기"]], "최초개최연도": raw[c["최초"]], "예산": raw[c["예산"]],
            "방문객": raw[c["방"]], "방문객_내": raw[c["내"]], "방문객_외": raw[c["외"]],
        })  # fmt: skip
        if year == 2026:
            d["계측방법"] = _strip_code(raw[29])
    else:
        raise ValueError(f"{year}년 양식은 아직 지원하지 않아요 (2024~2026만).")
    return standardize(d, year)


def standardize(d: pd.DataFrame, year: int) -> pd.DataFrame:
    """칸 이름을 맞춘 표를 정리한다. 엑셀 없이 테스트할 수 있게 따로 둔다."""
    d = d[d["연번"].notna() & d["축제명"].notna()].copy()
    d["연도"] = year
    d["방문객기준연도"] = year - 1
    d["시도"] = _strip_code(d["시도"])
    d["기초"] = _strip_code(d["기초"]).replace({"nan": "-", "": "-"})
    d["유형"] = d["유형_raw"].map(_map_type)
    d["장소유형"] = _nan_text_to_na(_strip_code(d["장소유형"]))
    d["개최주기"] = _nan_text_to_na(_strip_code(d["개최주기"]))
    for k in ["최초개최연도", "예산", "방문객", "방문객_내", "방문객_외"]:
        d[k] = _num(d[k])
    d.loc[d["방문객"] <= 0, "방문객"] = np.nan
    d["정규명"] = d["축제명"].map(norm_name)
    return d.reset_index(drop=True)


def link_panel(dfs: list[pd.DataFrame], thr: float = 0.82) -> pd.DataFrame:
    """연도별 표를 (시도, 기초, 정규명)으로 연결해 축제 ID(fid)를 붙인다.

    정확히 같은 이름을 먼저 찾고, 없으면 같은 지자체 안에서 이름 유사도로 찾는다.
    """
    allf = pd.concat(dfs, ignore_index=True)
    allf["fid"] = None
    reg: dict[tuple, list[tuple[str, str]]] = {}  # (시도, 기초) -> [(정규명, fid)]
    nid = 0
    for y in sorted(allf["연도"].unique()):
        used = set()
        for i in allf.index[allf["연도"] == y]:
            key = (allf.at[i, "시도"], allf.at[i, "기초"])
            nm = allf.at[i, "정규명"]
            cands = [(n, f) for n, f in reg.get(key, []) if f not in used]
            fid = next((f for n, f in cands if n == nm), None)
            if fid is None and cands and nm:
                best = max(cands, key=lambda c: difflib.SequenceMatcher(None, nm, c[0]).ratio())
                r = difflib.SequenceMatcher(None, nm, best[0]).ratio()
                short, long_ = sorted([nm, best[0]], key=len)
                if r >= thr or (len(short) >= 3 and short in long_):
                    fid = best[1]
            if fid is None:
                nid += 1
                fid = f"F{nid:05d}"
                reg.setdefault(key, []).append((nm, fid))
            used.add(fid)
            allf.at[i, "fid"] = fid
    latest = allf.sort_values("연도").groupby("fid")["유형"].last()
    allf["유형_원본"] = allf["유형"]
    allf["유형"] = allf["fid"].map(latest)
    return allf


# ---------- 태그와 트렌드 ----------


def add_tags(df: pd.DataFrame, col: str = "축제명") -> pd.DataFrame:
    s = df[col].astype(str)
    for t, pat in TAGS.items():
        df[t] = s.str.contains(pat, regex=True)
    return df


def _pct(z):
    return (np.exp(z) - 1) * 100


def tag_trends(panel, y0=2024, y1=2026, new_from=2023, min_n=10, min_new=10) -> pd.DataFrame:
    """소재·포맷 태그별 공급 트렌드.

    신설리프트 = (new_from년 이후 신설 중 태그 비율) ÷ (기존 중 태그 비율).
    판정: ↑(1.3 이상) + 신설 min_new개 이상 = 확실한 상승, ↑ + 신설 적음 = 관찰 대상,
    ↓(0.7 이하) = 성숙·감소, 나머지 = 정체. 방문객 성장은 [참고] 칸에만 둔다.
    """
    panel = add_tags(panel.copy())
    tags = list(TAGS)
    share = panel.groupby("연도")[tags].mean() * 100
    cur = panel[panel["연도"] == y1]
    new, old = cur[cur["최초개최연도"] >= new_from], cur[cur["최초개최연도"] < new_from]
    v = panel.pivot_table(index="fid", columns="연도", values="방문객", aggfunc="first")
    x = v[[y0, y1]].dropna()
    x = x[(x[y0] != x[y1]) & (x.min(axis=1) >= 100)]
    lg = np.log(x[y1] / x[y0])
    tag_by_fid = cur.set_index("fid")[tags]
    rng = np.random.default_rng(0)
    rows = []
    for t in tags:
        a, b = int(new[t].sum()), int(old[t].sum())
        lift = ((a + 0.5) / len(new)) / ((b + 0.5) / len(old))
        g = lg[lg.index.isin(tag_by_fid.index[tag_by_fid[t]])].values
        lo = hi = med = np.nan
        if len(g) >= 5:
            bs = [np.median(rng.choice(g, len(g))) for _ in range(2000)]
            med, lo, hi = (
                _pct(np.median(g)),
                _pct(np.percentile(bs, 2.5)),
                _pct(np.percentile(bs, 97.5)),
            )
        sup = "↑" if lift >= 1.3 else ("↓" if lift <= 0.7 else "→")
        if sup == "↑":
            judge = "확실한 상승" if a >= min_new else "관찰 대상(신설 적음)"
        elif sup == "↓":
            judge = "성숙·감소"
        else:
            judge = "정체"
        overall = _pct(lg.median())
        if np.isnan(lo):
            sig = ""
        elif lo > overall:
            sig = "평균보다 높음"
        elif hi < overall:
            sig = "평균보다 낮음"
        else:
            sig = "평균과 차이 없음"
        rows.append({
            "태그": t, f"축제수{y1}": int(cur[t].sum()), "신설수": a, "기존수": b,
            "신설리프트": lift, "공급신호": sup, "판정": judge,
            f"비중{y0}": share.loc[y0, t], f"비중{y1}": share.loc[y1, t],
            "공급변화p": share.loc[y1, t] - share.loc[y0, t],
            "[참고]방문객성장_중앙(%)": med, "[참고]95%구간_하한": lo, "[참고]95%구간_상한": hi,
            "[참고]성과n": len(g), "[참고]성과판단": sig,
        })  # fmt: skip
    out = pd.DataFrame(rows).set_index("태그")
    out = out[out[f"축제수{y1}"] >= min_n]
    out = out.sort_values(
        ["판정", "신설리프트"], key=lambda c: c.map(VERDICT_ORDER) if c.name == "판정" else -c
    )
    out.attrs["전체성장중앙"] = _pct(lg.median())
    out.attrs["기준"] = f"신설={new_from}년 이후 최초개최 {len(new)}개 / 기존={len(old)}개"
    return out.round(2)


def jeju_gap(panel: pd.DataFrame, year: int = 2026) -> pd.DataFrame:
    """태그별 전국·제주 축제 수와 비중. 제주 소재 강점(임시) = 제주 비중 ÷ 전국 비중."""
    cur = add_tags(panel[panel["연도"] == year].copy())
    jeju = cur[cur["시도"] == "제주"]
    tags = list(TAGS)
    out = pd.DataFrame({
        "전국건수": cur[tags].sum(), "전국%": cur[tags].mean() * 100,
        "제주건수": jeju[tags].sum(), "제주%": jeju[tags].mean() * 100 if len(jeju) else 0.0,
    })  # fmt: skip
    out["강점비"] = out["제주%"] / out["전국%"].replace(0, np.nan)
    out.attrs["제주축제수"] = len(jeju)
    return out


def jeju_festivals_by_month(panel: pd.DataFrame, year: int = 2026) -> dict[int, int]:
    """그 해 제주 축제의 월별 개수. 월을 모르는 축제는 세지 않는다."""
    months = panel[(panel["연도"] == year) & (panel["시도"] == "제주")]["월"].dropna().astype(int)
    counts = months.value_counts()
    return {m: int(counts.get(m, 0)) for m in range(1, 13)}


def tag_budgets(panel: pd.DataFrame, year: int = 2026) -> dict[str, pd.DataFrame]:
    """태그별 예산이 있는 축제 목록 (축제명, 예산_원), 예산 오름차순."""
    cur = add_tags(panel[(panel["연도"] == year) & (panel["예산"] > 0)].copy())
    out = {}
    for t in TAGS:
        rows = cur[cur[t]][["축제명", "예산"]].copy()
        rows["예산_원"] = (rows["예산"] * BUDGET_UNIT_KRW).round().astype("int64")
        out[t] = rows[["축제명", "예산_원"]].sort_values("예산_원").reset_index(drop=True)
    return out


# ---------- 저장과 읽기 ----------


def build_panel(raw_dir: Path = RAW_DIR, engine: str = "calamine") -> pd.DataFrame:
    dfs = [load_mcst(raw_dir / f"mcst_{y}.xlsx", y, engine=engine) for y in YEARS]
    return link_panel(dfs)


def load_panel(path: Path = PANEL_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"축제 패널 파일이 없어요: {path}. 먼저 `uv run python -m research.trends`로 만들어주세요."
        )
    return pd.read_parquet(path)


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    raw_dir = Path(argv[0]) if argv else RAW_DIR
    panel = build_panel(raw_dir)
    PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    panel.astype({"기간_raw": "string", "연번": "string", "장소명": "string"}).to_parquet(
        PANEL_PATH, index=False
    )
    print(panel.groupby("연도").size().to_string())
    print(f"저장: {PANEL_PATH}")


if __name__ == "__main__":
    main()
