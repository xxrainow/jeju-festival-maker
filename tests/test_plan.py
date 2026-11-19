import json
from datetime import UTC, datetime

import pytest

from agent.demo_cards import DEMO_REQUEST, demo_proposal
from agent.draft_contracts import PLAN_TEXT_SECTIONS, FestivalPlan
from agent.fake_checks import FAKE_TOOLS
from agent.llm import LLMError
from agent.plan import (
    SYSTEM_PROMPT,
    PlanGenerationError,
    PlanResponseError,
    allowed_numbers,
    generate_plan,
    krw_text,
    parse_plan_text,
    plan_payload,
    plan_to_markdown,
    save_plan,
)
from agent.verify import verify_idea

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
_DEMO = demo_proposal().ideas[0]
# 가짜 도구 시나리오(12월 실패 → 11월)를 쓰려고 추천 월만 12월로 바꾼 사본 (데모 카드는 1월)
_CARD = _DEMO.model_copy(
    update={"timing": _DEMO.timing.model_copy(update={"recommended_months": [12]})}
)
RUN = verify_idea(_CARD, DEMO_REQUEST, FAKE_TOOLS, festivals_by_month={11: 2})


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append((system, user))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)


def good_response(**override) -> dict:
    data = {
        "background": "시장·상권 형식은 신설 축제가 16개로 늘고 있고 제주에는 아직 같은 형식이 없다.",
        "concept": "수확철 감귤과 지역 가게가 함께 여는 주말 마켓을 제안한다.",
        "programs": [
            {"name": "감귤 직거래 장터", "description": "농가가 직접 파는 감귤 마켓"},
            {"name": "감귤 디저트 부스", "description": "지역 카페가 참여하는 시식 부스"},
        ],
        "promotion": "가족 대상이라 SNS와 마을 게시판을 함께 쓴다.",
        "operation": "장소와 인력은 미확인이며 셔틀 운영을 검토한다.",
        "risk": "대상 확인은 데이터 대기라 실데이터로 다시 확인한다.",
        "expected": "지역 가게 참여로 상권에 도움이 될 것으로 보인다.",
        "assumptions": ["참여할 감귤 농가를 모을 수 있다"],
    }
    return data | override


def test_krw_text():
    assert krw_text(10_000_000) == "1,000만 원"
    assert krw_text(175_500_000) == "1억 7,550만 원"
    assert krw_text(300_000_000) == "3억 원"
    assert krw_text(None) == "미확인"


def test_payload_uses_readable_money_and_final_card():
    payload = plan_payload(RUN, DEMO_REQUEST)
    assert payload["사용자 조건"]["예산 상한"] == "1,000만 원"
    assert payload["최종 아이디어"]["추천 시기"] == "11월"  # 루프에서 12월 → 11월로 바뀐 카드
    assert payload["예산 비교"]["같은 형식 예산 중간값"] == "6,000만 원"
    assert any("12" in c and "11" in c for c in payload["바뀐 점"])
    allowed = allowed_numbers(payload)
    assert {"16", "1000", "6000", "11"} <= allowed
    ok = good_response(promotion="10월부터 12월까지 SNS로 알린다.")
    assert parse_plan_text(json.dumps(ok, ensure_ascii=False), allowed)  # 월은 허용


def test_parse_rejects_unknown_numbers():
    allowed = allowed_numbers(plan_payload(RUN, DEMO_REQUEST))
    assert parse_plan_text(json.dumps(good_response(), ensure_ascii=False), allowed)
    bad = good_response(expected="방문객 5,000명과 매출 30% 증가가 예상된다.")
    with pytest.raises(PlanResponseError, match="입력에 없는 숫자"):
        parse_plan_text(json.dumps(bad, ensure_ascii=False), allowed)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"risk": ""}, "위험 관리"),
        ({"programs": [{"name": "하나", "description": ""}]}, "2~4개"),
        (
            {"programs": [{"name": "", "description": "a"}, {"name": "b", "description": "b"}]},
            "이름",
        ),
    ],
)
def test_parse_rejects_bad_shapes(override, message):
    allowed = allowed_numbers(plan_payload(RUN, DEMO_REQUEST))
    with pytest.raises(PlanResponseError, match=message):
        parse_plan_text(json.dumps(good_response(**override), ensure_ascii=False), allowed)


def test_generate_plan_fills_code_parts():
    llm = FakeLLM(good_response())
    plan = generate_plan(RUN, DEMO_REQUEST, llm, approved=True, now=NOW)
    assert isinstance(plan, FestivalPlan)
    assert llm.calls[0][0] == SYSTEM_PROMPT and "<input>" in llm.calls[0][1]
    assert plan.status == "draft" and plan.version == 1
    assert [s.key for s in plan.sections] == [k for k, _ in PLAN_TEXT_SECTIONS]
    assert plan.overview.period == "11월 중 (날짜 미확인)"
    assert plan.overview.venue == "미확인" and plan.overview.organizer == "미확인"
    assert plan.budget.format_median_krw == 60_000_000 and plan.budget.items == "미확인"
    # 상권 활성화 → 외지인 방문 증가율 + 카드 매출 증가율, 기준값·목표치는 데이터 대기
    assert [k.metric for k in plan.kpis] == ["외지인 방문 증가율", "카드 매출 증가율"]
    assert all(k.baseline.status == "pending" and k.target.status == "pending" for k in plan.kpis)
    assert plan.kpis[0].target.basis == ["2026 효돈감귤꽃축제", "제4회 의귀리 귤꽃축제"]
    assert [p.is_proposal for p in plan.programs] == [True, True]
    assert plan.changes and plan.changes[0].after == [11]
    assert plan.is_synthetic  # 가짜 확인 도구 결과
    assert "대상 확인 (데이터 대기)" in plan.unconfirmed
    labels = [e.label for e in plan.evidence]
    assert "예산 상한" in labels and any("신설 축제 수" in x for x in labels)


def test_retry_then_give_up():
    llm = FakeLLM("아님", good_response())
    assert generate_plan(RUN, DEMO_REQUEST, llm, approved=True, now=NOW)
    assert "이전 응답의 문제" in llm.calls[1][1]
    bad = good_response(background="예산 2억 원이 필요하다")
    with pytest.raises(PlanGenerationError, match="2회 시도"):
        generate_plan(RUN, DEMO_REQUEST, FakeLLM(bad, bad), approved=True, now=NOW)


def test_gates_and_errors(monkeypatch):
    with pytest.raises(PlanGenerationError, match="이대로 진행"):
        generate_plan(RUN, DEMO_REQUEST, FakeLLM(), approved=False)
    failed = RUN.model_copy(update={"outcome": "needs_other_idea"})
    with pytest.raises(PlanGenerationError, match="다른 아이디어"):
        generate_plan(failed, DEMO_REQUEST, FakeLLM(), approved=True)
    with pytest.raises(PlanGenerationError, match="AI 호출에 실패"):
        generate_plan(RUN, DEMO_REQUEST, FakeLLM(LLMError("한도")), approved=True)
    monkeypatch.setattr("agent.proposals.default_llm", lambda: None)
    with pytest.raises(PlanGenerationError, match="AI 설정이 없어요"):
        generate_plan(RUN, DEMO_REQUEST, approved=True)


def test_markdown_and_save(tmp_path):
    plan = generate_plan(RUN, DEMO_REQUEST, FakeLLM(good_response()), approved=True, now=NOW)
    md = plan_to_markdown(plan)
    for heading in ["사업 개요", "추진 배경", "목표·KPI", "세부 프로그램", "추진 일정", "예산 계획",
                    "위험 관리", "데이터 검증 결과 요약", "변경 이력", "데이터 출처"]:  # fmt: skip
        assert heading in md
    assert "가상 데이터로 낸 확인 결과" in md and "가짜" not in md
    assert "| 예산 | 1,000만 원 |" in md
    md_path, json_path = save_plan(plan, tmp_path)
    assert md_path.read_text(encoding="utf-8") == md
    assert (
        FestivalPlan.model_validate_json(json_path.read_text(encoding="utf-8")).plan_id
        == plan.plan_id
    )


def test_plan_groups_limitations_and_routes_operational_warnings():
    from agent.plan import build_limitations, plan_warning_notes

    duplicate_proxy = "외지인 방문은 와이파이 관광 사용량으로 대신 본 값이에요."
    festival = "같은 동네(애월읍) 다른 축제 '마을축제'가 같은 달에 있어요 (날짜 미확인)."
    shuttle = "야간 귀가 승차가 적은 후보 정류소가 있어요. 귀가 셔틀을 검토해 주세요."
    weather = "참고: 8월은 평소보다 더위가 많아요 (판정에는 쓰지 않음)."
    timing = "8월은 외지인 방문이 평소보다 약간 적은 달이에요 (지수 0.90)."
    run = RUN.model_copy(deep=True)
    checks = run.rounds[-1].results
    checks[0].warnings = [duplicate_proxy, weather, timing, timing]
    checks[1].warnings = [duplicate_proxy, shuttle, shuttle]
    checks[3].warnings = [festival, "정체는 교통량 가상 데이터로 계산했어요."]
    limitations = build_limitations(run.final, checks)
    assert len(limitations) == 5
    assert [s.split(":")[0] for s in limitations] == [
        "대리 지표", "가상 데이터", "데이터 범위", "방문객 수", "KPI"
    ]
    assert not any(w in " ".join(limitations) for w in (festival, shuttle, weather, timing))
    notes = plan_warning_notes(checks)
    assert notes["timing"] == [timing]
    assert notes["risk"].count(shuttle) == 1
    plan = generate_plan(run, DEMO_REQUEST, FakeLLM(good_response()), approved=True, now=NOW)
    assert plan.limitations == limitations
    risk = next(s.body for s in plan.sections if s.key == "risk")
    assert all(note in risk for note in (festival, shuttle, weather))
    md = plan_to_markdown(plan)
    overview = md.split("## 2.")[0]
    assert timing in overview
    assert md.count(shuttle) == 1
    assert md.count(timing) == 1
    # 이전 저장 데이터의 미분류 주의 문구도 표시할 때 분류·중복 제거한다.
    legacy = plan.model_copy(update={"limitations": [duplicate_proxy, shuttle, timing] * 8})
    assert plan_to_markdown(legacy) == md
    payload = plan_payload(run, DEMO_REQUEST)
    assert payload["시기 확인 참고"] == [timing]


def test_change_history_uses_plain_words():
    """변경 이력과 LLM 입력에 필드 이름(timing.recommended_months)을 그대로 쓰지 않는다."""
    plan = generate_plan(RUN, DEMO_REQUEST, FakeLLM(good_response()), approved=True, now=NOW)
    md = plan_to_markdown(plan)
    assert "- 추천 시기: 12월 → 11월 (" in md
    assert "timing.recommended_months" not in md
    payload = plan_payload(RUN, DEMO_REQUEST)
    assert payload["바뀐 점"][0].startswith("추천 시기: 12월 → 11월")
    assert not any("timing." in c for c in payload["바뀐 점"])


def test_venue_candidates_are_not_written_as_decided():
    """장소를 정하지 않았으면 후보 이름은 '후보'라고 밝힌 문장에서만 쓸 수 있다."""
    from agent.plan import unconfirmed_venue_claims

    names = ["곽지과물해변", "금산공원"]
    claim = "장소는 곽지과물해변을 활용한다. 셔틀을 검토한다."
    assert unconfirmed_venue_claims(claim, names) == ["곽지과물해변"]
    assert unconfirmed_venue_claims("후보인 곽지과물해변·금산공원 중에서 고른다.", names) == []
    allowed = allowed_numbers(plan_payload(RUN, DEMO_REQUEST))
    bad = good_response(operation=claim)
    with pytest.raises(PlanResponseError, match="정하지 않은 장소"):
        parse_plan_text(json.dumps(bad, ensure_ascii=False), allowed, names)
    ok = good_response(operation="장소는 미확인이고, 후보로 곽지과물해변을 검토한다.")
    assert parse_plan_text(json.dumps(ok, ensure_ascii=False), allowed, names)


def test_chosen_venue_goes_to_overview():
    """직접 고쳐서 다시 확인에서 사용자가 고른 장소는 개요에 쓰고, 후보 목록에서 뺀다."""
    from agent.draft_contracts import VenueCandidate

    final = RUN.final.model_copy(
        update={"venue": [VenueCandidate(name="곽지과물해변", admin_area="제주시 애월읍")]}
    )
    run = RUN.model_copy(update={"final": final})
    payload = plan_payload(run, DEMO_REQUEST)
    assert payload["최종 아이디어"]["장소"] == "곽지과물해변 (사용자 선택, 대관 조건 미확인)"
    assert "곽지과물해변" not in payload["최종 아이디어"]["장소 후보 (확정 아님)"]
    plan = generate_plan(run, DEMO_REQUEST, FakeLLM(good_response()), approved=True, now=NOW)
    assert plan.overview.venue.startswith("곽지과물해변")
    assert "| 장소 | 곽지과물해변 (사용자 선택" in plan_to_markdown(plan)


def test_free_text_purpose_picks_kpi():
    from agent.plan import build_kpis

    card = RUN.final
    req = DEMO_REQUEST.model_copy(update={"purpose": "관광객 좀 끌고 싶어요"})
    assert [k.metric for k in build_kpis(req, card)] == ["외지인 방문 증가율"]
    req2 = DEMO_REQUEST.model_copy(update={"purpose": "가게 매출 올리기"})
    assert [k.metric for k in build_kpis(req2, card)] == ["외지인 방문 증가율", "카드 매출 증가율"]
    req3 = DEMO_REQUEST.model_copy(update={"purpose": "마을 홍보"})
    assert [k.metric for k in build_kpis(req3, card)] == ["외지인 방문 증가율"]  # 기본 KPI


def test_approve_plan_and_require_approved():
    from agent.plan import PlanNotApprovedError, approve_plan, require_approved

    draft = generate_plan(RUN, DEMO_REQUEST, FakeLLM(good_response()), approved=True, now=NOW)
    with pytest.raises(PlanNotApprovedError, match="최종 승인"):
        require_approved(draft)
    later = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
    approved = approve_plan(draft, now=later)
    assert approved.status == "approved" and approved.approved_at == later
    assert draft.status == "draft" and draft.approved_at is None  # 원본은 그대로
    assert require_approved(approved) is approved
    assert approve_plan(approved) is approved  # 두 번 승인해도 같다
    assert "(v1, 승인)" in plan_to_markdown(approved)
    # JSON으로 저장했다 읽어도 계약 검사를 통과한다
    assert FestivalPlan.model_validate_json(approved.model_dump_json()).status == "approved"
    with pytest.raises(ValueError, match="approved_at"):
        FestivalPlan.model_validate(draft.model_dump() | {"status": "approved"})


def test_plan_document_uses_live_data_and_sixteen_sections():
    from app.plan_view import document_html

    plan = generate_plan(RUN, DEMO_REQUEST, FakeLLM(good_response()), approved=True, now=NOW)
    html = document_html(plan)
    assert html.count('<section class="fl-plan-section"') == 16
    assert '16. 데이터 출처' in html
    assert plan.overview.name in html and plan.overview.region in html
    assert '미확인' in html and '데이터 대기' in html
    assert all(s in html for s in ('대리 지표', '데이터 범위', '방문객 수', 'KPI'))
    assert '13. 변경 이력' in plan_to_markdown(plan)  # 저장용 문서의 추적 정보는 유지


def test_plan_document_escapes_generated_text_and_keeps_unknown_budget():
    from app.plan_view import document_html, rail_html

    plan = generate_plan(RUN, DEMO_REQUEST, FakeLLM(good_response()), approved=True, now=NOW)
    plan = plan.model_copy(update={
        'title': '<script>alert(1)</script>',
        'overview': plan.overview.model_copy(update={'budget_krw': None}),
        'assumptions': ['<img src=x onerror=alert(1)>'],
    })
    html = document_html(plan)
    assert '<script>' not in html and '<img src=x' not in html
    assert '&lt;script&gt;' in html and '&lt;img src=x' in html
    assert '예산 미확인' in html
    assert '&lt;script&gt;' in rail_html(plan, '<script>')


def test_plan_kpi_renders_zero_as_data_and_synthetic_notice_conditionally():
    from app.plan_view import document_html, rail_html

    plan = generate_plan(RUN, DEMO_REQUEST, FakeLLM(good_response()), approved=True, now=NOW)
    kpi = plan.kpis[0].model_copy(update={
        'baseline': plan.kpis[0].baseline.model_copy(update={'value': 0.0, 'status': 'ready'}),
    })
    plan = plan.model_copy(update={'kpis': [kpi], 'is_synthetic': False})
    assert '<p>0.0</p>' in document_html(plan)
    assert 'rail-note warning' not in rail_html(plan, '에이전트 추천안')
    synthetic = plan.model_copy(update={'is_synthetic': True})
    assert 'rail-note warning' in rail_html(synthetic, '에이전트 추천안')



def test_markdown_edit_saves_new_draft_and_updates_promo(tmp_path):
    from agent.plan import approve_plan
    from agent.plan_edit import edit_plan
    from app.promo import fixed_texts, promo_payload

    plan = generate_plan(RUN, DEMO_REQUEST, FakeLLM(good_response()), approved=True, now=NOW)
    approved = approve_plan(plan)
    source = plan_to_markdown(approved)
    edited = source.replace(f"| 축제명 | {plan.overview.name} |", "| 축제명 | 새 감귤 마켓 |")
    edited = edited.replace(f"| 장소 | {plan.overview.venue} |", "| 장소 | 사용자가 확인한 장소 |")
    edited = edited.replace(plan.programs[0].name, "감귤 가족 체험")
    revised = edit_plan(approved, edited)
    assert revised.version == plan.version + 1 and revised.status == "draft"
    assert revised.approved_at is None and revised.overview.name == "새 감귤 마켓"
    assert revised.overview.venue == "사용자가 확인한 장소"
    assert "감귤 가족 체험" in promo_payload(revised)["프로그램"]
    assert fixed_texts(revised)["title"] == "새 감귤 마켓"
    md, js = save_plan(revised, tmp_path)
    assert md.read_text() == plan_to_markdown(revised)
    restored = FestivalPlan.model_validate_json(js.read_text())
    assert restored.markdown_override == revised.markdown_override
    assert "v2, 초안" in plan_to_markdown(restored)
    assert "v2, 승인" in plan_to_markdown(approve_plan(restored))


def test_markdown_edit_rejects_missing_structure_without_modifying_original():
    from agent.plan_edit import edit_plan

    plan = generate_plan(RUN, DEMO_REQUEST, FakeLLM(good_response()), approved=True, now=NOW)
    source = plan_to_markdown(plan)
    assert edit_plan(plan, source) is plan
    for invalid in ("", "# 새 기획서", source.replace("## 4. 기본 컨셉", "## 삭제"),
                    source.replace("| 축제명 |", "| 삭제 |")):
        with pytest.raises(ValueError):
            edit_plan(plan, invalid)
    assert plan.markdown_override is None and plan.version == 1



def test_markdown_edit_keeps_document_design_and_unstructured_edits():
    from agent.plan_edit import edit_plan
    from app.plan_view import document_html

    plan = generate_plan(RUN, DEMO_REQUEST, FakeLLM(good_response()), approved=True, now=NOW)
    source = plan_to_markdown(plan)
    concept = next(s.body for s in plan.sections if s.key == "concept")
    revised = edit_plan(plan, source.replace(concept, "가족이 함께하는 수정된 마켓 컨셉입니다."))
    html = document_html(revised)
    assert "가족이 함께하는 수정된 마켓 컨셉입니다." in html
    assert html.count('<section class="fl-plan-section"') == 16
    assert 'fl-plan-table overview' in html and 'fl-plan-kpi' in html
    assert 'fl-plan-program' in html and 'fl-plan-table limitations' in html
    other = edit_plan(plan, source.replace("| --- | --- | --- |", "| --- | --- | --- |", 1)
                      .replace("## 7. 예산 계획", "## 7. 예산 계획\n\n사용자가 추가한 예산 안내"))
    html = document_html(other)
    assert "사용자가 추가한 예산 안내" in html
    assert 'fl-plan-kpi' in html and 'fl-plan-table overview' in html
