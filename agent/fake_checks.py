"""확인 도구 5개의 가짜 버전 (B의 실제 도구 연결 전, 루프·화면 연결·시연 연습용).

숫자는 실제 집계가 아니다. 모든 결과에 is_synthetic=True와 경고를 붙여 화면에 드러낸다.
시나리오는 기획서 7절 예시를 따른다: 12월이 들어 있으면 시기 확인이 실패하고 11월로 옮기라고 제안한다.
"""

from agent.draft_contracts import CheckResult, IdeaCard, Suggestion, UserRequest

FAKE_WARNING = "가짜 확인 도구 결과예요. 실제 제주 데이터로 계산한 값이 아니에요."
LOW_VISITOR_MONTHS = {12}  # 가짜 시나리오: 외지인 방문이 적다고 보는 달


def _result(check, status, reason, evidence=None, suggestion=None) -> CheckResult:
    return CheckResult(
        check=check,
        status=status,
        reason=reason,
        evidence=evidence or {},
        suggestion=suggestion,
        is_synthetic=True,
        warnings=[FAKE_WARNING],
    )


def check_timing(card: IdeaCard, request: UserRequest) -> CheckResult:
    months = card.timing.recommended_months
    low = sorted(set(months) & LOW_VISITOR_MONTHS)
    if not low:
        return _result("check_timing", "pass", "추천 월의 외지인 방문이 연평균 이상이에요.",
                       {"months": months, "outsider_visitors_index": None})  # fmt: skip
    better = [m for m in months if m not in LOW_VISITOR_MONTHS] or [11]
    return _result(
        "check_timing",
        "fail",
        f"{low[0]}월 {request.region or '해당 지역'} 외지인 방문이 연평균보다 낮아요.",
        {"months": months, "low_months": low, "outsider_visitors_index": None},
        Suggestion(field="timing.recommended_months", value=better, why="외지인 방문이 더 많은 달"),
    )


def check_venue(card: IdeaCard, request: UserRequest) -> CheckResult:
    return _result("check_venue", "conditional",
                   "관광객이 모이는 장소는 있지만 밤 귀가 버스가 적어 셔틀이 필요해 보여요.",
                   {"candidate_places": None, "night_bus_stops": None})  # fmt: skip


def check_target(card: IdeaCard, request: UserRequest) -> CheckResult:
    return _result("check_target", "pending", "유동인구 성·연령 데이터를 아직 받지 않았어요.")


def check_risk(card: IdeaCard, request: UserRequest) -> CheckResult:
    return _result("check_risk", "pass", "주거 밀집, 정체, 같은 재료 축제 충돌이 보이지 않아요.")


def check_budget(card: IdeaCard, request: UserRequest) -> CheckResult:
    if card.budget.scale == "소규모 버전" or card.budget.input_krw is None:
        return _result("check_budget", "pass", "입력 예산에 맞춘 규모예요.")
    return _result(
        "check_budget",
        "fail",
        "입력 예산이 같은 형식 예산 중앙값보다 작아요.",
        {"input_krw": card.budget.input_krw, "format_median_krw": card.budget.format_median_krw},
        Suggestion(field="budget.scale", value="소규모 버전", why="입력 예산에 맞춰 규모 축소"),
    )


FAKE_TOOLS = {
    "check_timing": check_timing,
    "check_venue": check_venue,
    "check_target": check_target,
    "check_risk": check_risk,
    "check_budget": check_budget,
}
