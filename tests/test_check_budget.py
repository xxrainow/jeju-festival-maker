from functools import partial

import pandas as pd

from agent.demo_cards import DEMO_REQUEST, demo_proposal
from agent.fake_checks import FAKE_TOOLS
from agent.fake_checks import check_budget as fake_check_budget
from agent.verify import verify_idea
from analytics.check_budget import (
    SMALL,
    SOURCE,
    budget_cases,
    check_budget,
    format_basis,
    visitors_estimate,
)
from analytics.real_checks import REAL_TOOLS

CARD = demo_proposal().ideas[0]
FMT = "시장·상권"


def panel(n_market=6, year=2026) -> pd.DataFrame:
    """시장·상권 n개 (예산 10·20·…백만 원) + 다른 축제. 예산 단위는 원자료처럼 백만 원."""
    rows = []
    for i in range(n_market):
        rows.append((f"전통시장 축제{i}", 10.0 * (i + 1), 1000.0 * (i + 1), "주민화합", "계측"))
    for i in range(6):
        rows.append((f"주민 화합 한마당{i}", 5.0 * (i + 1), 500.0, "주민화합", "계측"))
    rows.append(("예산 없는 시장", 0.0, 100.0, "주민화합", "계측"))
    df = pd.DataFrame(rows, columns=["축제명", "예산", "방문객", "유형", "계측방법"])
    old = df.assign(연도=2024, 예산=df["예산"] * 0.1)  # 중단·이전 연도 행은 계산에서 빠져야 함
    df = pd.concat([df.assign(연도=year), old], ignore_index=True)
    return df.assign(시도="강원", 기초="정선군")


def card(fmt=FMT, scale="기본", median=None, budget=None):
    b = CARD.budget.model_copy(
        update={"scale": scale, "format_median_krw": median, "input_krw": budget}
    )
    return CARD.model_copy(update={"format": fmt, "budget": b})


def request(budget):
    return DEMO_REQUEST.model_copy(update={"budget_max_krw": budget})


CASES = budget_cases(panel())


def test_units_and_only_2026_rows():
    rows = format_basis(CASES, FMT).rows
    assert len(rows) == 6  # 예산 0원과 2024년 행 제외
    assert rows["budget_krw"].min() == 10_000_000  # 백만 원 → 원
    assert rows["region"].iloc[0] == "강원 정선군"


def test_no_budget_passes_with_median_as_reference():
    r = check_budget(card(), request(None), CASES)
    fake = fake_check_budget(card(), request(None))
    assert r.check == fake.check == "check_budget"
    assert r.status == "pass" and r.suggestion is None and not r.is_synthetic
    assert r.evidence["format_median_krw"] == 35_000_000  # 10~60백만 원의 중간값
    assert "기준 예산" in r.reason and r.sources == [SOURCE]


def test_budget_at_or_above_median_passes():
    r = check_budget(card(), request(35_000_000), CASES)
    assert r.status == "pass" and r.evidence["scale"] == "기본"


def test_below_median_with_cases_is_conditional_small_version():
    r = check_budget(card(), request(25_000_000), CASES)
    assert r.status == "conditional" and r.suggestion is None
    assert r.evidence["scale"] == SMALL
    ex = r.evidence["small_examples"]
    assert [e["budget_krw"] for e in ex] == [20_000_000, 10_000_000]  # 입력에 가까운 것부터
    assert set(ex[0]) == {"name", "budget_krw", "visitors", "region", "year"}
    assert any("지자체가 신고한 값" in w for w in r.warnings)


def test_no_cases_fails_then_small_version_is_conditional():
    r = check_budget(card(scale="기본"), request(5_000_000), CASES)
    assert r.status == "fail"
    assert (r.suggestion.field, r.suggestion.value) == ("budget.scale", SMALL)
    assert "기간을 하루로" in r.suggestion.why
    r = check_budget(card(scale=SMALL), request(5_000_000), CASES)
    assert r.status == "conditional" and r.suggestion is None
    assert any("비슷한 규모 사례 없음" in w for w in r.warnings)


def test_verify_loop_does_not_keep_failing():
    tools = {**FAKE_TOOLS, **REAL_TOOLS}
    assert tools["check_budget"] is check_budget
    tools["check_budget"] = partial(check_budget, cases=CASES)
    tools["check_timing"] = FAKE_TOOLS["check_timing"]  # 시기는 가짜로 고정
    c = card(scale="기본").model_copy(
        update={"timing": CARD.timing.model_copy(update={"recommended_months": [11]})}
    )
    run = verify_idea(c, request(5_000_000), tools)
    assert run.rounds[0].changes[0].after == SMALL
    assert run.rounds[-1].results[-1].status == "conditional"
    assert run.outcome == "ready_for_approval"


def test_few_tag_cases_fall_back_to_type():
    cases = budget_cases(panel(n_market=3))
    basis = format_basis(cases, FMT)
    assert not basis.by_tag and "문체부 유형 '주민화합'" in basis.label
    r = check_budget(card(), request(None), cases)
    assert "유형" in r.evidence["basis"]
    assert any("유형으로 계산" in w for w in r.warnings)


def test_card_median_mismatch_warns():
    r = check_budget(card(median=99_000_000), request(None), CASES)
    assert any("카드의 같은 형식 중간값" in w for w in r.warnings)
    r = check_budget(card(median=35_000_000), request(None), CASES)
    assert not any("카드의 같은 형식 중간값" in w for w in r.warnings)


def test_visitors_estimate_uses_measured_per_capita():
    rows = format_basis(CASES, FMT).rows  # 1인당 10,000원으로 모두 같음
    est = visitors_estimate(10_000_000, rows, CASES)
    assert est["low"] == est["high"] == 1000 and est["scope"] == "같은 기준"
    few = rows.head(2)  # 계측 5건 미만이면 전체 계측 축제로
    assert "전체 계측 축제" in visitors_estimate(10_000_000, few, CASES)["scope"]


def test_real_median_matches_card_median():
    """A의 카드(research.trends.tag_budgets)와 같은 중간값인지 실제 패널로 확인."""
    from typing import get_args

    from agent.draft_contracts import FestivalFormat
    from research.trends import load_panel, tag_budgets

    p = load_panel()
    budgets, cases = tag_budgets(p), budget_cases(p)
    for fmt in get_args(FestivalFormat):
        a = int(budgets[fmt]["예산_원"].median())
        assert int(format_basis(cases, fmt).rows["budget_krw"].median()) == a, fmt
