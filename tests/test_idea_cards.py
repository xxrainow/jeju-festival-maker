import json

import pytest

from agent.demo_cards import DEMO_REQUEST, demo_proposal
from agent.draft_contracts import UserRequest
from agent.idea_cards import (
    SYSTEM_PROMPT,
    CardGenerationError,
    CardResponseError,
    build_user_prompt,
    generate_idea_cards,
    parse_picks,
)
from agent.idea_gen import SEED_MATERIALS, build_candidates
from agent.llm import LLMError
from agent.proposals import propose_idea_cards

REQUEST = UserRequest(
    region="제주시 애월읍", purpose="지역 상권 활성화", interest="감귤", season="겨울",
    budget_max_krw=10_000_000,
)  # fmt: skip


class FakeLLM:
    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def picks_for(cset, ids, **override) -> str:
    rows = []
    for n, cid in enumerate(ids, 1):
        row = {
            "candidate_id": cid,
            "title": f"감귤 축제 {'가나다'[n - 1]}",
            "concept": "감귤로 여는 하루 축제",
            "pick_reason": "형식이 서로 달라요",
            "hypotheses": ["12월 애월읍 외지인 방문이 충분하다"],
        }
        rows.append(row | override)
    return json.dumps({"picks": rows}, ensure_ascii=False)


def distinct_ids(cset, k=3):
    seen, ids = set(), []
    for c in cset.candidates:
        if c.format not in seen:
            seen.add(c.format)
            ids.append(c.candidate_id)
    return ids[:k]


def test_prompt_lists_candidates_as_json(trend_data):
    cset = build_candidates(REQUEST, trend_data)
    prompt = build_user_prompt(REQUEST, cset, trend_data)
    assert "<candidates>" in prompt and "cand_01" in prompt
    assert "목록에 없는 조합을 만들지 마세요" in SYSTEM_PROMPT


def test_parse_picks_accepts_valid_response(trend_data):
    cset = build_candidates(REQUEST, trend_data)
    ids = distinct_ids(cset)
    picks = parse_picks("```json\n" + picks_for(cset, ids) + "\n```", cset)
    assert [p["candidate"].candidate_id for p in picks] == ids


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda ids: ids[:2], "3개가 아니라 2개"),
        (lambda ids: [ids[0], ids[1], "cand_99"], "목록에 없는 후보"),
        (lambda ids: [ids[0], ids[0], ids[1]], "같은 후보"),
    ],
)
def test_parse_picks_rejects_bad_ids(trend_data, mutate, message):
    cset = build_candidates(REQUEST, trend_data)
    with pytest.raises(CardResponseError, match=message):
        parse_picks(picks_for(cset, mutate(distinct_ids(cset))), cset)


def test_parse_picks_rejects_same_format(trend_data):
    cset = build_candidates(UserRequest(), trend_data)
    first = cset.candidates[0]
    same = [c.candidate_id for c in cset.candidates if c.format == first.format][:2]
    other = next(c.candidate_id for c in cset.candidates if c.format != first.format)
    with pytest.raises(CardResponseError, match="형식"):
        parse_picks(picks_for(cset, [*same, other]), cset)


def test_parse_picks_rejects_numbers_in_text(trend_data):
    cset = build_candidates(REQUEST, trend_data)
    ids = distinct_ids(cset)
    with pytest.raises(CardResponseError, match="숫자"):
        parse_picks(picks_for(cset, ids, concept="방문객 5만 명이 오는 축제"), cset)
    with pytest.raises(CardResponseError, match="월·시각이 아닌 숫자"):
        parse_picks(picks_for(cset, ids, hypotheses=["매출 30% 증가"]), cset)
    ok = picks_for(cset, ids, hypotheses=["12월 18시 이후에도 버스가 있다"])
    assert parse_picks(ok, cset)


def test_generate_retries_with_problem_then_builds_cards(trend_data):
    cset = build_candidates(REQUEST, trend_data)
    ids = distinct_ids(cset)
    llm = FakeLLM("응답 아님", picks_for(cset, list(reversed(ids))))
    proposal = generate_idea_cards(REQUEST, trend_data, llm)
    assert "이전 응답의 문제: 응답이 JSON이 아니에요." in llm.calls[1][1]
    assert [c.rank for c in proposal.ideas] == [1, 2, 3]
    # 순위는 LLM 순서가 아니라 점수 순서
    scores = [c.score for c in proposal.ideas]
    assert scores == sorted(scores, reverse=True)
    assert proposal.ideas[0].evidence.trend.source.startswith("문체부")
    assert not proposal.is_demo


def test_generate_gives_up_after_attempts(trend_data):
    llm = FakeLLM("x", "y")
    with pytest.raises(CardGenerationError, match="2회 시도"):
        generate_idea_cards(REQUEST, trend_data, llm)


def test_generate_wraps_llm_error(trend_data):
    with pytest.raises(CardGenerationError, match="AI 호출에 실패"):
        generate_idea_cards(REQUEST, trend_data, FakeLLM(LLMError("시간 초과")))


def test_too_few_formats_is_reported(trend_data):
    req = UserRequest(interest="용천수", season="겨울")  # 용천수 7~8월 → 겨울에 후보 없음
    with pytest.raises(CardGenerationError, match="3개보다 적어요"):
        generate_idea_cards(req, trend_data, FakeLLM())


def test_demo_entry_point_works_offline():
    proposal = propose_idea_cards(DEMO_REQUEST)
    assert proposal.is_demo and proposal.notices
    assert [c.title for c in proposal.ideas] == [c.title for c in demo_proposal().ideas]
    assert proposal.ideas[0].evidence.trend.new_lift == 3.6


def test_real_path_needs_llm():
    with pytest.raises(CardGenerationError, match="AI 공급자"):
        propose_idea_cards(DEMO_REQUEST, demo=False)


def test_real_path_with_fake_llm(trend_data):
    cset = build_candidates(REQUEST, trend_data)
    llm = FakeLLM(picks_for(cset, distinct_ids(cset)))
    proposal = propose_idea_cards(
        REQUEST, demo=False, llm=llm, data=trend_data, materials=SEED_MATERIALS
    )
    assert len(proposal.ideas) == 3
