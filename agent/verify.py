"""고른 아이디어의 검증·수정 루프 (설계 기획서 7절, 9-3절).

확인 도구 5개를 돌리고, 실패(fail)한 항목의 제안대로 고친 뒤 다시 확인한다.
- 고칠 수 있는 칸: timing.recommended_months, venue, budget.scale, programs
- format, material(아이디어의 핵심)은 바꾸지 않는다
- 처음 확인 1회 + 고친 뒤 재확인 최대 MAX_FIXES회. 그래도 fail이 남으면 다른 아이디어를 고르게 한다
- pending(데이터 대기)은 실패로 세지 않는다

확인 도구는 B가 만든다(회의에서 담당 확정). 연결 전에는 agent/fake_checks.py의 가짜 도구로 돌린다.
"""

from collections.abc import Callable, Mapping
from typing import Any

from agent.draft_contracts import (
    CheckName,
    CheckResult,
    CheckRound,
    IdeaCard,
    IdeaChange,
    Suggestion,
    UserRequest,
    VerificationRun,
)

MAX_FIXES = 3
CHECK_ORDER: tuple[CheckName, ...] = (
    "check_timing",
    "check_venue",
    "check_target",
    "check_risk",
    "check_budget",
)

CheckTool = Callable[[IdeaCard, UserRequest], CheckResult]


def run_checks(
    card: IdeaCard, request: UserRequest, tools: Mapping[str, CheckTool]
) -> list[CheckResult]:
    """도구 5개를 정해진 순서로 돌린다. 연결되지 않은 도구는 pending으로 남긴다."""
    results = []
    for name in CHECK_ORDER:
        tool = tools.get(name)
        if tool is None:
            results.append(_pending(name, "아직 연결되지 않은 확인 도구예요."))
            continue
        result = tool(card, request)
        if result.check != name:
            raise ValueError(f"{name} 도구가 {result.check} 결과를 돌려줬어요.")
        results.append(result)
    return results


def _pending(name: CheckName, why: str) -> CheckResult:
    return CheckResult(check=name, status="pending", reason=why, warnings=[why])


def _get(card: IdeaCard, field: str) -> Any:
    data = card.model_dump(mode="json")
    if field == "timing.recommended_months":
        return data["timing"]["recommended_months"]
    if field == "budget.scale":
        return data["budget"]["scale"]
    return data[field]


def apply_suggestions(
    card: IdeaCard,
    suggestions: list[Suggestion],
    festivals_by_month: Mapping[int, int] | None = None,
) -> tuple[IdeaCard, list[IdeaChange]]:
    """제안을 카드에 적용한다. 값이 그대로인 제안은 바뀐 점에 넣지 않는다.

    추천 월이 바뀌면 그 달의 제주 축제 수도 다시 센다 (festivals_by_month가 없으면 null로 둔다).
    결과 카드는 계약으로 다시 검사한다 (잘못된 값이면 ValidationError).
    """
    data = card.model_dump(mode="json")
    changes = []
    for s in suggestions:
        before = _get(card, s.field)
        if before == s.value:
            continue
        if s.field == "timing.recommended_months":
            data["timing"]["recommended_months"] = s.value
            data["timing"]["jeju_festivals_in_month"] = (
                sum(festivals_by_month.get(m, 0) for m in s.value) if festivals_by_month else None
            )
        elif s.field == "budget.scale":
            data["budget"]["scale"] = s.value
        else:  # venue, programs
            data[s.field] = s.value
        changes.append(IdeaChange(field=s.field, before=before, after=s.value, why=s.why))
    return IdeaCard.model_validate(data), changes


def verify_idea(
    card: IdeaCard,
    request: UserRequest,
    tools: Mapping[str, CheckTool],
    *,
    max_fixes: int = MAX_FIXES,
    festivals_by_month: Mapping[int, int] | None = None,
) -> VerificationRun:
    """검증·수정 루프. 결과의 rounds가 사용자 확인 화면의 "바뀐 점"과 시연용 실행 기록이 된다."""
    if not 0 <= max_fixes <= MAX_FIXES:
        raise ValueError(f"max_fixes는 0~{MAX_FIXES}이어야 해요.")
    current = card
    rounds: list[CheckRound] = []
    for number in range(1, max_fixes + 2):
        results = run_checks(current, request, tools)
        fails = [r for r in results if r.status == "fail"]
        if not fails or number == max_fixes + 1:
            rounds.append(CheckRound(round=number, results=results))
            break
        # 고칠 방법이 없는 실패가 있으면 더 돌리지 않는다
        if any(r.suggestion is None for r in fails):
            rounds.append(CheckRound(round=number, results=results))
            break
        updated, changes = apply_suggestions(
            current, [r.suggestion for r in fails], festivals_by_month
        )
        rounds.append(CheckRound(round=number, results=results, changes=changes))
        if not changes:  # 같은 제안만 반복되면 고쳐도 소용없다
            break
        current = updated

    last_fails = [r for r in rounds[-1].results if r.status == "fail"]
    return VerificationRun(
        original=card,
        final=current,
        rounds=rounds,
        outcome="needs_other_idea" if last_fails else "ready_for_approval",
    )


def summarize(run: VerificationRun) -> list[str]:
    """사용자 확인 화면에 보여줄 "바뀐 점과 이유" 문장."""
    lines = []
    for r in run.rounds:
        for c in r.changes:
            lines.append(f"{c.field}: {c.before} → {c.after} ({c.why})")
    if run.outcome == "needs_other_idea":
        left = [x.check for x in run.rounds[-1].results if x.status == "fail"]
        lines.append(f"고쳐도 통과하지 못한 확인: {', '.join(left)}. 다른 아이디어를 골라보세요.")
    return lines
