"""시연 중 발견한 지역·예산·소재·장소 검사 회귀 사례."""
import json

import pytest
from test_idea_cards import FakeLLM, distinct_ids, picks_for
from test_plan import DEMO_REQUEST, RUN, good_response

from agent.draft_contracts import UserRequest
from agent.idea_cards import (
    CardGenerationError,
    CardResponseError,
    generate_idea_cards,
    parse_picks,
)
from agent.idea_gen import SEED_MATERIALS, build_candidates, resolve_interest
from agent.plan import PlanResponseError, allowed_numbers, parse_plan_text, plan_payload
from agent.proposals import propose_idea_cards
from agent.request_parser import jeju_areas, resolve_region


def test_numbered_dong_names_do_not_trigger_card_retry(trend_data):
    request = UserRequest(region="제주시 일도2동", interest="감귤")
    cset = build_candidates(request, trend_data)
    raw = picks_for(cset, distinct_ids(cset), concept="일도2동 감귤 장터")
    llm = FakeLLM(raw)
    result = generate_idea_cards(request, trend_data, llm)
    assert len(result.ideas) == 3 and len(llm.calls) == 1


def test_other_region_in_title_is_rejected(trend_data):
    request = UserRequest(region="서귀포시 표선면", interest="감귤")
    cset = build_candidates(request, trend_data)
    raw = json.loads(picks_for(cset, distinct_ids(cset)))
    raw["picks"][0]["title"] = "추자도 참굴비 축제"
    with pytest.raises(CardResponseError, match="다른 지역"):
        parse_picks(json.dumps(raw), cset, request, trend_data)


def test_small_card_rejects_drone_show_but_accepts_existing_lights(trend_data):
    cset = build_candidates(DEMO_REQUEST, trend_data)
    for concept, rejected in (("감귤 드론 쇼", True), ("기존 조명을 활용한 감귤 산책", False)):
        raw = picks_for(cset, distinct_ids(cset), concept=concept)
        if rejected:
            with pytest.raises(CardResponseError, match="드론"):
                parse_picks(raw, cset, DEMO_REQUEST, trend_data)
        else:
            assert parse_picks(raw, cset, DEMO_REQUEST, trend_data)


@pytest.mark.parametrize("sentence", [
    "곽지과물해변은 대관 가능 여부가 미확인이다.",
    "곽지과물해변을 검토 중이다.",
    "곽지과물해변은 협의 후 결정한다.",
])
def test_uncertain_venue_does_not_trigger_plan_retry(sentence):
    allowed = allowed_numbers(plan_payload(RUN, DEMO_REQUEST))
    assert parse_plan_text(json.dumps(good_response(operation=sentence)), allowed, ["곽지과물해변"])


def test_candidate_word_does_not_hide_definite_venue_claim():
    allowed = allowed_numbers(plan_payload(RUN, DEMO_REQUEST))
    raw = good_response(operation="후보를 검토했으며 곽지과물해변에서 개최한다.")
    with pytest.raises(PlanResponseError, match="정하지 않은 장소"):
        parse_plan_text(json.dumps(raw), allowed, ["곽지과물해변"])


def test_small_plan_rejects_drone_program():
    raw = good_response(programs=[
        {"name": "드론 쇼", "description": "드론 군집 공연"},
        {"name": "감귤 장터", "description": "지역 농가 참여"},
    ])
    allowed = allowed_numbers(plan_payload(RUN, DEMO_REQUEST))
    with pytest.raises(PlanResponseError, match="드론"):
        parse_plan_text(json.dumps(raw), allowed, request=DEMO_REQUEST, constrained=True)


def test_unknown_budget_cannot_borrow_amount_from_reference():
    request = UserRequest()
    for text, rejected in (("총예산은 1,000만 원으로 운영한다.", True),
                           ("참고 사례 예산은 1,000만 원이다.", False)):
        raw = good_response(operation=text)
        if rejected:
            with pytest.raises(PlanResponseError, match="예산을 입력하지"):
                parse_plan_text(json.dumps(raw), {"1000", "16"}, request=request)
        else:
            assert parse_plan_text(json.dumps(raw), {"1000", "16"}, request=request)


def test_demo_preserves_missing_and_explicit_budget():
    for budget in (None, 3_000_000):
        proposal = propose_idea_cards(UserRequest(budget_max_krw=budget), demo=True)
        assert proposal.input.budget_max_krw == budget
        assert all(c.budget.input_krw == budget for c in proposal.ideas)
        assert all(e.budget_krw <= budget for c in proposal.ideas for e in c.budget.small_examples)


def test_demo_keeps_explicit_example_notice_for_other_regions():
    request = UserRequest(region="서귀포시 표선면")
    proposal = propose_idea_cards(request, demo=True)
    assert proposal.is_demo and any("예시" in note for note in proposal.notices)
    assert proposal.input.region == "제주시 애월읍"  # 고정 예시와 실제 입력의 차이를 화면이 안내
    assert proposal.input.budget_max_krw is None


def test_unknown_material_does_not_switch_to_other_materials(trend_data):
    with pytest.raises(ValueError, match="다른 재료로 바꾸지"):
        resolve_interest("미등록소재XYZ", SEED_MATERIALS)
    llm = FakeLLM()
    with pytest.raises(CardGenerationError, match="미등록소재XYZ"):
        generate_idea_cards(UserRequest(interest="미등록소재XYZ"), trend_data, llm)
    assert not llm.calls


def test_ildodong_returns_ambiguous_choices():
    area, note = resolve_region("일도동", jeju_areas())
    assert area is None
    assert "일도1동" in note and "일도2동" in note and "여러 곳" in note
