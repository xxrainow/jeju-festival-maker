"""규모 확인 도구 check_budget의 실제 버전 (agent/fake_checks.py check_budget과 같은 입출력).

판정 기준 (설계 문서): 같은 형식 하위권 사례가 있으면 조건부, 없으면 규모 축소안 제시.
예산 때문에 형식을 빼지 않고 "소규모 버전"으로 보여준다.

| 상황 | 결과 |
|---|---|
| 예산 입력 없음 | pass, 같은 형식 중간값을 기준 예산으로 제시 |
| 입력 ≥ 같은 형식 중간값 | pass |
| 입력 < 중간값, 입력 이하로 연 같은 형식 사례 있음 | conditional, "소규모 버전" + 사례 최대 3개 |
| 입력 이하 사례 없음, 카드 scale "기본" | fail, budget.scale → "소규모 버전" 제안 + 줄이는 방법 |
| 입력 이하 사례 없음, 카드 scale 이미 "소규모 버전" | conditional + "비슷한 규모 사례 없음" 경고 |

- 계약(budget.scale)은 "기본"/"소규모 버전" 두 값뿐이라 "축소"는 "소규모 버전"을 뜻한다
- 사례: 문체부 2026 계획, 예산 > 0 (A의 research.trends.tag_budgets와 같은 범위라 카드 중간값과 같다).
  중단된 축제는 계산하지 않는다 (설계 문서 3절)
- 형식 태그 사례가 MIN_CASES 미만이면 그 형식 축제에 가장 많은 문체부 유형(5개)으로 대신 계산한다
- 예산 단위: 원자료 백만 원 → 원 (research.trends.BUDGET_UNIT_KRW)

바꿔 끼우기: from analytics.real_checks import REAL_TOOLS; tools = {**FAKE_TOOLS, **REAL_TOOLS}
"""

from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from agent.draft_contracts import CheckResult, IdeaCard, Suggestion, UserRequest

SOURCE = "문체부 지역축제 개최계획 2024~2026 (예산은 계획 기준)"
YEAR = 2026
MIN_CASES = 5
MAX_EXAMPLES = 3
MEASURED = "계측"
SMALL = "소규모 버전"
VISITOR_WARNING = (
    "방문객 수는 지자체가 신고한 값이라 참고로만 보세요. 1인당 비용은 방문객을 '계측'했다고 "
    "답한 축제만으로 계산했어요."
)
REDUCTION_METHODS = [
    "기간을 하루로 줄이기",
    "프로그램을 핵심 2~3개로 줄이기",
    "무대·음향은 기존 시설이나 마을 장비 쓰기",
    "홍보는 SNS·마을 방송 위주로 하기",
]


def budget_cases(panel: pd.DataFrame, year: int = YEAR) -> pd.DataFrame:
    """그해 예산이 있는 축제 + 형식 태그. budget_krw는 원 단위."""
    from research.trends import BUDGET_UNIT_KRW, add_tags

    cur = add_tags(panel[(panel["연도"] == year) & (panel["예산"] > 0)].copy())
    cur["budget_krw"] = (cur["예산"] * BUDGET_UNIT_KRW).round().astype("int64")
    gu = cur["기초"].fillna("-").astype(str)
    cur["region"] = cur["시도"].astype(str) + gu.where(gu != "-", "").map(
        lambda g: f" {g}" if g else ""
    )
    return cur.reset_index(drop=True)


@dataclass
class Basis:
    rows: pd.DataFrame
    label: str  # 예: "형식 태그 '시장·상권'" 또는 "문체부 유형 '주민화합' (형식 태그 사례 3건이라 대신 씀)"
    by_tag: bool


def format_basis(cases: pd.DataFrame, fmt: str, min_cases: int = MIN_CASES) -> Basis:
    rows = cases[cases[fmt]] if fmt in cases else cases.iloc[0:0]
    if len(rows) >= min_cases:
        return Basis(rows, f"형식 태그 '{fmt}'", True)
    kind = rows["유형"].mode().iloc[0] if len(rows) else None
    if kind is None:
        return Basis(rows, f"형식 태그 '{fmt}' (사례 {len(rows)}건)", True)
    label = f"문체부 유형 '{kind}' (형식 태그 사례가 {len(rows)}건뿐이라 대신 씀)"
    return Basis(cases[cases["유형"] == kind], label, False)


def visitors_estimate(
    budget_krw: int, basis_rows: pd.DataFrame, all_cases: pd.DataFrame
) -> dict | None:
    """예산 ÷ 계측 1인당 비용(하위 25%~상위 25%) → 대략 방문객 범위."""

    def per_capita(df):
        m = df[(df["계측방법"] == MEASURED) & (df["방문객"] > 0)]
        return m["budget_krw"] / m["방문객"]

    pc, scope = per_capita(basis_rows), "같은 기준"
    if len(pc) < MIN_CASES:
        pc, scope = per_capita(all_cases), f"전체 계측 축제 (같은 기준 계측 {len(pc)}건뿐)"
    if len(pc) < MIN_CASES:
        return None
    q25, q75 = pc.quantile(0.25), pc.quantile(0.75)
    return {
        "low": int(round(budget_krw / q75, -2)),
        "high": int(round(budget_krw / q25, -2)),
        "per_capita_krw_q25": round(q25),
        "per_capita_krw_q75": round(q75),
        "sample_count": len(pc),
        "scope": scope,
    }


def _won(krw: int) -> str:
    """예: 74,000,000 → "7,400만 원"."""
    if krw >= 100_000_000:
        return f"{krw / 100_000_000:,.2f}".rstrip("0").rstrip(".") + "억 원"
    return f"{krw / 10_000:,.0f}만 원"


def _example(r) -> dict:
    return {
        "name": r["축제명"],
        "budget_krw": int(r["budget_krw"]),
        "visitors": None if pd.isna(r["방문객"]) else int(r["방문객"]),
        "region": r["region"],
        "year": int(r["연도"]),
    }


@lru_cache(maxsize=1)
def load_budget_cases() -> pd.DataFrame:
    """A의 카드와 같은 패널(research.trends.load_panel)을 읽는다."""
    from research.trends import load_panel

    return budget_cases(load_panel())


def check_budget(
    card: IdeaCard, request: UserRequest, cases: pd.DataFrame | None = None
) -> CheckResult:
    cases = load_budget_cases() if cases is None else cases
    fmt = card.format
    budget = request.budget_max_krw or card.budget.input_krw
    basis = format_basis(cases, fmt)
    rows = basis.rows
    warnings = [VISITOR_WARNING]
    evidence: dict = {
        "input_krw": budget,
        "format_median_krw": None,
        "card_scale": card.budget.scale,
    }
    if rows.empty:
        reason = f"'{fmt}' 형식의 {YEAR}년 예산 사례가 없어 규모를 확인하지 못했어요."
        return CheckResult(
            check="check_budget",
            status="pending",
            reason=reason,
            evidence=evidence,
            sources=[SOURCE],
            warnings=[reason],
        )

    median = int(rows["budget_krw"].median())
    q25 = int(rows["budget_krw"].quantile(0.25))
    if not basis.by_tag:
        warnings.append(f"{basis.label}. 형식 태그 대신 유형으로 계산했어요.")
    if card.budget.format_median_krw not in (None, median):
        warnings.append(
            f"카드의 같은 형식 중간값({_won(card.budget.format_median_krw)})과 "
            f"확인 도구 값({_won(median)})이 달라요. 카드를 만든 뒤 자료가 바뀌었을 수 있어요."
        )
    examples = []
    if budget is not None:
        under = rows[rows["budget_krw"] <= budget].sort_values("budget_krw", ascending=False)
        examples = [_example(r) for _, r in under.head(MAX_EXAMPLES).iterrows()]
    estimate = visitors_estimate(budget or median, rows, cases)
    evidence.update(
        {
            "format_median_krw": median,
            "format_q25_krw": q25,
            "basis": basis.label,
            "sample_count": len(rows),
            "small_examples": examples,
            "visitors_estimate": estimate,
            "year": YEAR,
        }
    )
    if estimate:
        evidence["visitors_estimate_text"] = (
            f"{_won(budget or median)}이면 대략 {estimate['low']:,}~{estimate['high']:,}명 규모 "
            f"(계측 1인당 {estimate['per_capita_krw_q25']:,}~{estimate['per_capita_krw_q75']:,}원, "
            f"{estimate['scope']} {estimate['sample_count']}건)"
        )

    suggestion = None
    head = f"같은 형식({basis.label}, {YEAR}년 {len(rows)}건) 예산 중간값은 {_won(median)}이에요."
    if budget is None:
        status, scale = "pass", "기본"
        reason = f"예산 입력이 없어요. {head} 이 금액을 기준 예산으로 보세요."
    elif budget >= median:
        status, scale = "pass", "기본"
        reason = f"입력 예산 {_won(budget)}이 중간값 이상이에요. {head}"
    elif examples:
        status, scale = "conditional", SMALL
        names = ", ".join(f"{e['name']}({_won(e['budget_krw'])})" for e in examples)
        reason = (
            f"입력 예산 {_won(budget)}이 중간값보다 작지만, 이 예산 이하로 연 같은 형식 사례가 "
            f"있어요: {names}. {SMALL}으로 진행해요. {head}"
        )
    elif card.budget.scale != SMALL:
        status, scale = "fail", SMALL
        reason = (
            f"입력 예산 {_won(budget)} 이하로 연 같은 형식 사례가 없어요. {head} "
            f"하위 25%도 {_won(q25)}이에요."
        )
        suggestion = Suggestion(
            field="budget.scale",
            value=SMALL,
            why=f"입력 예산에 맞춰 규모 축소: {', '.join(REDUCTION_METHODS)}",
        )
    else:
        status, scale = "conditional", SMALL
        reason = (
            f"이미 {SMALL}이지만 입력 예산 {_won(budget)} 이하로 연 같은 형식 사례는 없어요. {head}"
        )
        warnings.append(
            f"비슷한 규모 사례 없음. 줄이는 방법: {', '.join(REDUCTION_METHODS)}. "
            "비용 항목별 견적을 직접 확인해 주세요."
        )
    evidence["scale"] = scale
    if status != "pass" or budget is None:
        evidence["reduction_methods"] = REDUCTION_METHODS if scale == SMALL else []
    return CheckResult(
        check="check_budget",
        status=status,
        reason=reason,
        evidence=evidence,
        sources=[SOURCE],
        suggestion=suggestion,
        is_synthetic=False,
        warnings=warnings,
    )
