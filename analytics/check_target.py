"""대상 확인 도구 check_target의 실제 버전 (agent/fake_checks.py check_target과 같은 입출력).

기준 (설계 문서 9-3): 입력 대상의 연령대 비중이 그 동네에서 제주 평균 이상인가.

- 자료: 와이파이 장소별 사용자 현황(성·연령, 실데이터)이 기본. 4-11 유동인구가 있으면 evidence에 같이 보여주고,
  가짜 데이터면 evidence flow에만 "가상 데이터"로 표시한다. 판정은 와이파이 실데이터라 결과 is_synthetic=False
- 비중 = 그 동네 와이파이 장소 사용자 중 대상 연령대(성별) 비율, 카드 추천 월만.
  제주 평균 = 행정동·읍면 표에 들어간 모든 장소의 같은 비율
- 배수 = 동네 비중 ÷ 제주 평균. 1.0 이상 pass, 그 미만 conditional (fail은 쓰지 않는다)
  - 대상은 사용자가 정한 값이라 Agent가 고칠 수 없다. 0.9 미만이면 "홍보 대상을 넓히거나 장소를 바꿔보세요" 경고만
  - 이 동네에서 비중이 높은 연령대는 evidence와 경고로 알린다
- 성별 대상(여성, 엄마 등)이 있으면 성별 비중도 같은 기준으로 보고, 나쁜 쪽을 결과로 쓴다
- 표시 자릿수: 비중이 같아 보이거나(0.1% vs 0.1%) 배수가 기준과 어긋나 보이면 자릿수를 늘린다
- pending: 대상이 없거나 연령대로 바꿀 수 없는 문구, 지역 없음, 그 동네 자료 없음

대상 문구 → 연령대 규칙은 TARGET_RULES (문서: docs/b-guide.md 9절).
"""

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from agent.draft_contracts import CheckResult, IdeaCard, UserRequest
from analytics.check_timing import ADMIN_BUILD_NOTE, LOW_DATA_NOTICE, precise
from analytics.periods import CANDIDATE_PERIOD

DEMOGRAPHICS_PATH = Path("data/processed/wifi_users_demographics.csv")
WIFI_SOURCE = "와이파이 장소별 사용자 현황 (성·연령)"
AGE_BANDS = ["10대 미만", "10대", "20대", "30대", "40대", "50대", "60대 이상"]
PASS_RATIO = 1.0
CONDITIONAL_RATIO = 0.9
MIN_USERS_SHARE = 0.1  # 동네 사용자 수가 동네 중앙값의 10% 미만이면 자료 적음 (추자면 3%)
MIN_TARGET_USERS = 100
STRONG_RATIO = 1.1  # 이 동네에서 비중이 높은 연령대로 알려줄 기준
ELDERLY_WARNING = (
    "와이파이 자료는 2020년 7월 이후 60대 이상·10대 미만이 거의 집계되지 않아요 "
    "(50대로 합쳐진 것으로 보여요). 이 연령대는 판정에서 빼요."
)
# 원본에 거의 집계되지 않는 연령대 (2023~2025 제주 전체 비중 60대 이상 0.1%, 10대 미만 0.005%).
# 2020-07부터 60대 이상이 급감하고 50대가 늘었다 (docs/data-check.md 2-2)
UNMEASURED_AGES = ("10대 미만", "60대 이상")
COUNT_WARNING = (
    "와이파이 사용자 수는 장소·월마다 따로 센 값이라 같은 사람이 여러 번 들어갈 수 있어요. "
    "사람 수가 아니라 비중으로만 봐요."
)

# (문구 정규식, 연령대, 규칙 이름). 여러 개가 걸리면 연령대를 합친다
TARGET_RULES: list[tuple[str, set[str], str]] = [
    (r"가족|부모|자녀|엄마|아빠", {"10대 미만", "30대", "40대"}, "가족: 30~40대 + 10대 미만"),
    (r"영유아|유아|어린이|키즈|아이", {"10대 미만"}, "영유아·어린이: 10대 미만"),
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
    """대상은 사용자가 정한 값이라 낮아도 fail이 아니라 conditional (Agent가 고칠 수 없다)."""
    if ratio is None:
        return "pending"
    return "pass" if ratio >= PASS_RATIO else "conditional"


def _is_low(ratio: float | None) -> bool:
    return ratio is not None and ratio < CONDITIONAL_RATIO


def _compare(demo, region, months, ages, sex) -> dict | None:
    d = demo[demo["month"].isin(months)]
    dong, jeju = _share(d[d["admin_area"] == region], ages, sex), _share(d, ages, sex)
    if dong is None or not jeju:
        return None
    return share_numbers(dong, jeju)


def _pct_pair(dong: float, jeju: float) -> tuple[float, float]:
    """두 비중(%)이 반올림으로 같아 보이지 않을 만큼 자릿수를 늘린다 (최대 소수 셋째 자리)."""
    a, b = dong * 100, jeju * 100
    for d in (1, 2, 3):
        if round(a, d) != round(b, d) or a == b:
            return round(a, d), round(b, d)
    return round(a, 3), round(b, 3)


def share_numbers(dong: float, jeju: float) -> dict:
    """동네·제주 비중(%)과 배수. 표시가 판정 기준(1.0·0.9배)과 어긋나지 않게 자릿수를 맞춘다."""
    dong_pct, jeju_pct = _pct_pair(dong, jeju)
    return {
        "dong_share_pct": dong_pct,
        "jeju_share_pct": jeju_pct,
        "ratio": precise(dong / jeju, (PASS_RATIO, CONDITIONAL_RATIO)),
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


def check_target(
    card: IdeaCard,
    request: UserRequest,
    demographics: pd.DataFrame | None = None,
    use_flow: bool = True,
) -> CheckResult:
    demo = load_demographics() if demographics is None else demographics
    months = sorted(set(card.timing.recommended_months))
    ages, sex, rules = parse_target(request.target)
    # 자료가 거의 없는 연령대는 판정에서 뺀다 (가족 → 30·40대만)
    excluded = [a for a in UNMEASURED_AGES if a in ages]
    target_ages = sorted(ages, key=AGE_BANDS.index)
    ages = ages - set(excluded)
    evidence: dict = {"target": request.target, "age_groups": sorted(ages, key=AGE_BANDS.index),
                      "target_age_groups": target_ages, "excluded_age_groups": excluded,
                      "sex": sex, "target_rules": rules, "months": months}  # fmt: skip
    if excluded and ages:
        evidence["excluded_note"] = f"{'·'.join(excluded)}은 자료가 거의 없어 제외"

    def pending(why: str, *extra: str) -> CheckResult:
        return CheckResult(check="check_target", status="pending", reason=why,
                           evidence=evidence, warnings=[why, *extra, ELDERLY_WARNING])  # fmt: skip

    if not request.target:
        return pending("대상이 입력되지 않아 확인하지 않았어요.")
    if excluded and not ages:  # 어르신, 영유아처럼 자료가 거의 없는 연령대뿐
        return pending(
            f"와이파이 자료에 {'·'.join(excluded)}이 거의 집계되지 않아 확인할 수 없어요."
        )
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
    if note := evidence.get("excluded_note"):
        detail += f" ({note})"
    suggestion = None  # 대상은 사용자가 정한 값이라 고치는 제안을 하지 않는다
    low = any(_is_low(p["ratio"]) for p in parts.values() if p)
    if status == "pass":
        reason = f"{request.region}의 대상({label}) 비중이 제주 평균 이상이에요: {detail}."
    elif not low:
        reason = f"{request.region}의 대상({label}) 비중이 제주 평균보다 조금 낮아요: {detail}."
    else:
        reason = f"{request.region}의 대상({label}) 비중이 제주 평균보다 낮아요: {detail}."
        warnings.append(
            f"이 동네는 {request.target} 비중이 제주 평균보다 낮아요. "
            "홍보 대상을 넓히거나 장소를 바꿔보세요."
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
