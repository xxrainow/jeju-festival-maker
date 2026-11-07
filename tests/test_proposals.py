import json

import pytest

from agent.demo import DEMO_CASES, DEMO_IDEAS
from agent.ideas import IDEA_COUNT, IdeaGenerationError, parse_ideas
from agent.proposals import DEMO_NOTICE, IdeaProposal, propose_ideas
from schemas.contracts import UserRequest

REQUEST = UserRequest(region="제주시 애월읍", purpose="지역 상권 활성화")


def test_demo_proposal_has_three_ideas_and_notice():
    proposal = propose_ideas(REQUEST)
    assert proposal.is_demo is True
    assert DEMO_NOTICE in proposal.notices
    assert len(proposal.ideas) == IDEA_COUNT
    assert proposal.request == REQUEST


def test_demo_ideas_cite_only_included_cases():
    proposal = propose_ideas(REQUEST)
    case_ids = {case.case_id for case in proposal.cases}
    for idea in proposal.ideas:
        assert idea.case_ids
        assert set(idea.case_ids) <= case_ids
        assert [c.case_id for c in proposal.cases_for(idea)] == idea.case_ids


def test_demo_ideas_pass_the_same_checks_as_llm_output():
    # 데모도 실제 LLM 응답과 같은 검사를 통과해야 화면이 같은 모양을 받는다
    raw = json.dumps(
        {"ideas": [idea.model_dump(exclude={"idea_id", "status"}) for idea in DEMO_IDEAS]},
        ensure_ascii=False,
    )
    parsed = parse_ideas(raw, {case.case_id for case in DEMO_CASES})
    assert [i.title for i in parsed] == [i.title for i in DEMO_IDEAS]


def test_demo_cases_are_marked_synthetic():
    for case in DEMO_CASES:
        assert case.title.startswith("[가상]")
        assert case.source_url.host == "example.com"


def test_changing_returned_ideas_does_not_change_demo_source():
    proposal = propose_ideas(REQUEST)
    proposal.ideas[0].programs.append("바뀐 프로그램")
    assert "바뀐 프로그램" not in propose_ideas(REQUEST).ideas[0].programs


def test_proposal_round_trips_as_json():
    # 화면에서 st.session_state에 dict로 저장했다가 다시 읽을 수 있어야 한다
    data = propose_ideas(REQUEST).model_dump(mode="json")
    restored = IdeaProposal.model_validate(data)
    assert restored.ideas[2].case_ids == ["case_demo_coffee", "case_demo_village"]


def test_real_mode_is_not_connected_yet():
    with pytest.raises(IdeaGenerationError, match="아직 연결 전"):
        propose_ideas(REQUEST, demo=False)
