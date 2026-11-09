import pytest
from pydantic import ValidationError

from agent.demo_cards import DEMO_REQUEST, demo_proposal
from agent.draft_contracts import CheckResult, Suggestion
from agent.fake_checks import FAKE_TOOLS, FAKE_WARNING
from agent.verify import CHECK_ORDER, apply_suggestions, run_checks, summarize, verify_idea

CARD = demo_proposal().ideas[0]  # 애월 감귤 로컬 마켓, 추천 12월


def fixed(check, status, suggestion=None):
    def tool(card, request):
        return CheckResult(check=check, status=status, reason="r", suggestion=suggestion)

    return tool


def test_demo_scenario_moves_december_to_november():
    run = verify_idea(CARD, DEMO_REQUEST, FAKE_TOOLS, festivals_by_month={11: 2, 12: 1})
    assert run.outcome == "ready_for_approval"
    assert len(run.rounds) == 2
    assert run.rounds[0].results[0].status == "fail"
    change = run.rounds[0].changes[0]
    assert (change.field, change.before, change.after) == ("timing.recommended_months", [12], [11])
    assert run.final.timing.recommended_months == [11]
    assert run.final.timing.jeju_festivals_in_month == 2
    assert run.original.timing.recommended_months == [12]  # 원본은 그대로
    assert run.final.format == CARD.format and run.final.material == CARD.material
    assert all(FAKE_WARNING in r.warnings and r.is_synthetic for r in run.rounds[0].results)
    assert summarize(run) == ["timing.recommended_months: [12] → [11] (외지인 방문이 더 많은 달)"]


def test_results_follow_fixed_order_and_missing_tools_are_pending():
    results = run_checks(CARD, DEMO_REQUEST, {"check_risk": fixed("check_risk", "pass")})
    assert [r.check for r in results] == list(CHECK_ORDER)
    assert [r.status for r in results] == ["pending", "pending", "pending", "pass", "pending"]


def test_pending_is_not_failure():
    run = verify_idea(CARD, DEMO_REQUEST, {})
    assert run.outcome == "ready_for_approval" and len(run.rounds) == 1


def test_tool_returning_wrong_check_name_is_error():
    with pytest.raises(ValueError, match="check_venue"):
        run_checks(CARD, DEMO_REQUEST, {"check_timing": fixed("check_venue", "pass")})


def test_gives_up_after_three_fixes():
    calls = {"n": 0}

    def always_fail(card, request):
        calls["n"] += 1
        months = [(calls["n"] % 12) + 1]
        return CheckResult(
            check="check_timing", status="fail", reason="계속 실패",
            suggestion=Suggestion(field="timing.recommended_months", value=months, why="다른 달"),
        )  # fmt: skip

    run = verify_idea(CARD, DEMO_REQUEST, {"check_timing": always_fail})
    assert run.outcome == "needs_other_idea"
    assert len(run.rounds) == 4  # 처음 1회 + 고친 뒤 3회
    assert sum(len(r.changes) for r in run.rounds) == 3
    assert "다른 아이디어" in summarize(run)[-1]


def test_fail_without_suggestion_stops_immediately():
    run = verify_idea(CARD, DEMO_REQUEST, {"check_risk": fixed("check_risk", "fail")})
    assert run.outcome == "needs_other_idea" and len(run.rounds) == 1


def test_repeating_same_suggestion_stops():
    same = Suggestion(field="timing.recommended_months", value=[12], why="그대로")
    run = verify_idea(CARD, DEMO_REQUEST, {"check_timing": fixed("check_timing", "fail", same)})
    assert run.outcome == "needs_other_idea" and len(run.rounds) == 1
    assert run.rounds[0].changes == []


def test_apply_venue_programs_and_scale():
    card, changes = apply_suggestions(
        CARD,
        [
            Suggestion(field="venue", value=[{"name": "한담해변", "admin_area": "제주시 애월읍"}],
                       why="관광객 비중 상위"),
            Suggestion(field="programs", value=["감귤 따기"], why="체험 추가"),
            Suggestion(field="budget.scale", value="기본", why="예산 충분"),
        ],
    )  # fmt: skip
    assert card.venue[0].name == "한담해변"
    assert card.programs == ["감귤 따기"]
    assert card.budget.scale == "기본"
    assert [c.field for c in changes] == ["venue", "programs", "budget.scale"]


def test_bad_suggestion_value_is_rejected_by_contract():
    with pytest.raises(ValidationError):
        apply_suggestions(
            CARD, [Suggestion(field="timing.recommended_months", value=[13], why="x")]
        )


def test_max_fixes_range():
    with pytest.raises(ValueError):
        verify_idea(CARD, DEMO_REQUEST, FAKE_TOOLS, max_fixes=4)
