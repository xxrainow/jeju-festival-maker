"""대상 확인 도구 check_target의 실제 버전 (agent/fake_checks.py check_target과 같은 입출력).

기준 (설계 문서 9-3): 입력 대상의 연령대 비중이 그 동네에서 제주 평균 이상인가.

- 자료: 와이파이 장소별 사용자 현황(성·연령, 실데이터)이 기본. 4-11 유동인구가 있으면 evidence에 같이 보여주고,
  가짜 데이터면 evidence flow에만 "가상 데이터"로 표시한다. 판정은 와이파이 실데이터라 결과 is_synthetic=False
- 비중 = 그 동네 와이파이 장소 사용자 중 대상 연령대(성별) 비율, 카드 추천 월만.
  제주 평균 = 행정동·읍면 표에 들어간 모든 장소의 같은 비율
- 배수 = 동네 비중 ÷ 제주 평균. 1.0 이상 pass, 0.9 이상 conditional, 그 미만 fail
- 성별 대상(여성, 엄마 등)이 있으면 성별 비중도 같은 기준으로 보고, 나쁜 쪽을 결과로 쓴다
- fail 제안: 같은 동네에서 대상 배수가 1.0 이상인 다른 달 중 가장 높은 달 (재료 제철 안에서).
  대상은 고칠 수 있는 칸이 아니라서, 이 동네에서 비중이 높은 연령대는 evidence와 경고로만 알린다
- pending: 대상이 없거나 연령대로 바꿀 수 없는 문구, 지역 없음, 그 동네 자료 없음

대상 문구 → 연령대 규칙은 TARGET_RULES (문서: docs/b-guide.md 9절).
"""

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from agent.draft_contracts import CheckResult, IdeaCard, Suggestion, UserRequest
from analytics.check_timing import ADMIN_BUILD_NOTE, LOW_DATA_NOTICE
from analytics.periods import CANDIDATE_PERIOD

DEMOGRAPHICS_PATH = Path("data/processed/wifi_users_demographics.csv")
WIFI_SOURCE = "와이파이 장소별 사용자 현황 (성·연령)"
AGE_BANDS = ["10대 미만", "10대", "20대", "30대", "40대", "50대", "60대 이상"]
PASS_RATIO = 1.0
CONDITIONAL_RATIO = 0.9
MIN_USERS_SHARE = 0.1  # 동네 사용자 수가 동네 중앙값의 10% 미만이면 자료 적음 (추자면 3%)
MIN_TARGET_USERS = 100
STRONG_RATIO = 1.1  # 이 동네에서 비중이 높은 연령대로 알려줄 기준
ELDERLY_WARNING = "와이파이 사용자 기준이라 고령층(60대 이상)이 실제보다 적게 잡힐 수 있어요."
COUNT_WARNING = (
    "와이파이 사용자 수는 장소·월마다 따로 센 값이라 같은 사람이 여러 번 들어갈 수 있어요. "
    "사람 수가 아니라 비중으로만 봐요."
)

# (문구 정규식, 연령대, 규칙 이름). 여러 개가 걸리면 연령대를 합친다
TARGET_RULES: list[tuple[str, set[str], str]] = [
    (r"가족|아이|어린이|키즈|유아|부모|자녀", {"10대 미만", "30대", "40대"}, "가족: 30~40대 + 10대 미만"),
    (r"청소년|중학생|고등학생|10대(?! ?미만)", {"10대"}, "청소년: 10대"),
    (r"청년|대학생|MZ|젊은|2030", {"20대", "30대"}, "청년: 20~30대"),
    (r"중장년|중년|장년|4050", {"40대", "50대"}, "중장년: 40~50대"),
    (r"어르신|노인|시니어|고령|노년|실버", {"60대 이상"}, "어르신: 60대 이상"),
]  # fmt: skip
SEX_RULES = [(r"여성|여자|엄마|주부", "여성"), (r"남성|남자|아빠", "남성")]
_DECADE = {1: "10대", 2: "20대", 3: "30대", 4: "40대", 5: "50대", 6: "60대 이상", 7: "60대 이상"}


def parse_target(text: str | None) -> tuple[set[str], str | None, list[str]]:
    """대상 문구 → (연령대, 성별, 적용한 규칙). 예: "20~30대 여성" → ({20대, 30대}, 여성, [...])."""
    if not text:
        return set(), None, []
    ages, rules = set(), []
    for pattern, bands, name in TARGET_RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            ages |= bands
            rules.append(name)
    for lo, hi in re.findall(r"([1-7])0\s*[~\-–]\s*([1-7])0\s*대", text):
        bands = {_DECADE[d] for d in range(int(lo), int(hi) + 1)}
        ages |= bands
        rules.append(f"{lo}0~{hi}0대")
    if re.search(r"10\s*대\s*미만|영유아", text):
        ages.add("10대 미만")
        rules.append("10대 미만")
    for d in re.findall(r"(?<![~\-–\d])([2-7])0\s*대", text):
        ages.add(_DECADE[int(d)])
        rules.append(f"{d}0대")
    sex = next((s for pattern, s in SEX_RULES if re.search(pattern, text)), None)
    if sex:
        rules.append(f"성별: {sex}")
    return ages, sex, list(dict.fromkeys(rules))


def build_demographics(users: pd.DataFrame, places: pd.DataFrame) -> pd.DataFrame:
    """동네 × 달(1~12) × 성 × 연령대 사용자 수 (CANDIDATE_PERIOD 합계)."""
    u = CANDIDATE_PERIOD.filter_months(users).merge(
        places[["wifi_place_name", "admin_area"]], on="wifi_place_name"
    )
    u = u.assign(month=u["base_year_month"].str[4:].astype(int))
    out = (
        u.groupby(["admin_area", "month", "sex", "age_range"])["user_count"]
        .sum()
        .astype("int64")
        .rename("users")
        .reset_index()
    )
    first, last = u["base_year_month"].min(), u["base_year_month"].max()
    out["source"] = f"{WIFI_SOURCE} {first[:4]}-{first[4:]} ~ {last[:4]}-{last[4:]}"
    return out


@lru_cache(maxsize=1)
def load_demographics() -> pd.DataFrame | None:
    from analytics.reference_data import reference_first

    path = reference_first(DEMOGRAPHICS_PATH.name, DEMOGRAPHICS_PATH)  # analytics/reference/ 먼저
    if not path.exists():
        return None
    return pd.read_csv(path, encoding="utf-8-sig")


def _share(df: pd.DataFrame, ages: set[str], sex: str | None) -> float | None:
    total = df["users"].sum()
    if not total:
        return None
    mask = df["age_range"].isin(ages) if ages else pd.Series(True, index=df.index)
    if sex:
        mask &= df["sex"] == sex
    return float(df.loc[mask, "users"].sum() / total)


def _status(ratio: float | None) -> str:
    if ratio is None:
        return "pending"
    if ratio >= PASS_RATIO:
        return "pass"
    return "conditional" if ratio >= CONDITIONAL_RATIO else "fail"


def _compare(demo, region, months, ages, sex) -> dict | None:
    d = demo[demo["month"].isin(months)]
    dong, jeju = _share(d[d["admin_area"] == region], ages, sex), _share(d, ages, sex)
    if dong is None or not jeju:
        return None
    return {
        "dong_share_pct": round(dong * 100, 1),
        "jeju_share_pct": round(jeju * 100, 1),
        "ratio": round(dong / jeju, 2),
    }


def flow_evidence(region: str, ages: set[str], sex: str | None) -> dict | None:
    """4-11 방문인구로 본 같은 비중 (보여주기만, 판정에는 안 씀)."""
    from analytics.flow_source import load_flow

    flow = load_flow()
    if flow is None:
        return None
    f = flow.data.rename(columns={"age_band": "age_range", "visit_pop_cnt": "users"})
    dong, jeju = _share(f[f["emd_nm"] == region], ages, sex), _share(f, ages, sex)
    if dong is None or not jeju:
        return None
    return {
        "dong_share_pct": round(dong * 100, 1),
        "jeju_share_pct": round(jeju * 100, 1),
        "ratio": round(dong / jeju, 2),
        "measure": "방문인구(visit_pop_cnt)",
        "source": flow.label,
        "is_synthetic": flow.is_synthetic,
        "data_label": "가상 데이터" if flow.is_synthetic else "실데이터",
    }


def _season(material: str) -> list[int] | None:
    from analytics.check_timing import load_timing_data

    season = load_timing_data().material_season.get(material)
    return season[0] if season else None


def check_target(
    card: IdeaCard,
    request: UserRequest,
    demographics: pd.DataFrame | None = None,
    season: list[int] | None = None,
    use_flow: bool = True,
) -> CheckResult:
    demo = load_demographics() if demographics is None else demographics
    months = sorted(set(card.timing.recommended_months))
    ages, sex, rules = parse_target(request.target)
    evidence: dict = {"target": request.target, "age_groups": sorted(ages, key=AGE_BANDS.index),
                      "sex": sex, "target_rules": rules, "months": months}  # fmt: skip

    def pending(why: str, *extra: str) -> CheckResult:
        return CheckResult(check="check_target", status="pending", reason=why,
                           evidence=evidence, warnings=[why, *extra, ELDERLY_WARNING])  # fmt: skip

    if not request.target:
        return pending("대상이 입력되지 않아 확인하지 않았어요.")
    if not ages and not sex:
        return pending(
            f"대상 '{request.target}'을(를) 연령대로 바꾸지 못했어요. "
            "가족, 청소년, 청년, 중장년, 어르신, 20~30대, 여성 같은 말로 입력해 주세요."
        )
    if not request.region:
        return pending("지역이 없어 동네와 제주 평균을 비교하지 못했어요.")
    if demo is None:
        return pending(
            "와이파이 성·연령 표가 아직 없어요. 관리자에게 표 만들기를 요청해 주세요.",
            ADMIN_BUILD_NOTE,
        )
    if demo[demo["admin_area"] == request.region].empty:
        return pending(f"{request.region}에는 와이파이 사용자 자료가 없어요.")

    sources = [demo["source"].iloc[0]]
    warnings = [ELDERLY_WARNING, COUNT_WARNING]
    # 자료가 적은 동네: 사용자 수가 동네 중앙값의 MIN_USERS_SHARE 미만, 대상 사용자가 MIN_TARGET_USERS명 미만
    totals = demo.groupby("admin_area")["users"].sum()
    low_data = []
    if totals[request.region] < totals.median() * MIN_USERS_SHARE:
        low_data.append(
            f"와이파이 사용자가 동네 중앙값의 {totals[request.region] / totals.median():.0%}뿐이에요"
        )
    if ages:
        dong = demo[(demo["admin_area"] == request.region) & demo["month"].isin(months)]
        target_users = int(dong.loc[dong["age_range"].isin(ages), "users"].sum())
        if target_users < MIN_TARGET_USERS:
            low_data.append(f"추천 월 대상 연령대 사용자가 {target_users}명뿐이에요")
    evidence["low_data"] = low_data
    if low_data:
        warnings.append(f"{LOW_DATA_NOTICE}: {', '.join(low_data)}.")
    parts = {}
    if ages:
        parts["age"] = _compare(demo, request.region, months, ages, None)
    if sex:
        parts["sex"] = _compare(demo, request.region, months, set(), sex)
    evidence["age_share"] = parts.get("age")
    evidence["sex_share"] = parts.get("sex")
    statuses = [_status(p["ratio"] if p else None) for p in parts.values()]
    status = max(statuses, key={"pending": -1, "pass": 0, "conditional": 1, "fail": 2}.get)

    # 이 동네에서 제주 평균보다 비중이 높은 연령대 (대상 대안 참고)
    region_rows = demo[demo["admin_area"] == request.region]
    strong = []
    for band in AGE_BANDS:
        c = _compare(demo, request.region, list(range(1, 13)), {band}, None)
        if c and c["ratio"] >= STRONG_RATIO:
            strong.append({"age_group": band, "ratio": c["ratio"]})
    evidence["strong_age_groups"] = sorted(strong, key=lambda x: -x["ratio"])
    by_month = []
    for m in range(1, 13):
        if region_rows[region_rows["month"] == m].empty:
            continue
        ratios = [_compare(demo, request.region, [m], ages, None) if ages else None,
                  _compare(demo, request.region, [m], set(), sex) if sex else None]  # fmt: skip
        ratio = min(r["ratio"] for r in ratios if r) if any(ratios) else None
        by_month.append({"month": m, "ratio": ratio})
    evidence["ratio_by_month"] = by_month

    if use_flow and (flow := flow_evidence(request.region, ages, sex)):
        evidence["flow"] = flow
        sources.append(flow["source"])
        if flow["is_synthetic"]:
            warnings.append(
                "참고로 보여 주는 4-11 유동인구 비중은 가상 데이터예요. 판정은 와이파이 실데이터로만 했어요."
            )

    label = " · ".join(evidence["age_groups"] + ([sex] if sex else []))
    detail = ", ".join(
        f"{'연령' if k == 'age' else '성별'} {p['dong_share_pct']}% (제주 평균 {p['jeju_share_pct']}%, {p['ratio']}배)"
        for k, p in parts.items()
        if p
    )
    suggestion = None
    if status == "pass":
        reason = f"{request.region}의 대상({label}) 비중이 제주 평균 이상이에요: {detail}."
    elif status == "conditional":
        reason = f"{request.region}의 대상({label}) 비중이 제주 평균보다 조금 낮아요: {detail}."
    else:
        reason = f"{request.region}의 대상({label}) 비중이 제주 평균보다 낮아요: {detail}."
        season = _season(card.material) if season is None else season
        options = [
            x for x in by_month
            if x["ratio"] is not None and x["ratio"] >= PASS_RATIO and x["month"] not in months
            and (not season or x["month"] in season)
        ]  # fmt: skip
        if options:
            best = max(options, key=lambda x: x["ratio"])
            suggestion = Suggestion(
                field="timing.recommended_months",
                value=[best["month"]],
                why=f"{request.region}에서 대상 비중이 제주 평균의 {best['ratio']}배인 {best['month']}월로 바꿔요.",
            )
        else:
            warnings.append(
                "대상 비중이 평균 이상인 다른 달이 없어 추천 월을 고치는 제안을 하지 못했어요."
            )
        if strong:
            text = ", ".join(
                f"{s['age_group']}({s['ratio']}배)" for s in evidence["strong_age_groups"]
            )
            warnings.append(
                f"참고: {request.region}에서 제주 평균보다 비중이 높은 연령대는 {text}예요."
            )
    return CheckResult(
        check="check_target",
        status=status,
        reason=reason,
        evidence=evidence,
        sources=sources,
        suggestion=suggestion,
        is_synthetic=False,  # 판정은 와이파이 실데이터
        warnings=warnings,
    )
