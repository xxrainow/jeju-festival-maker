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
RUN = verify_idea(demo_proposal().ideas[0], DEMO_REQUEST, FAKE_TOOLS, festivals_by_month={11: 2})


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
    assert "가짜·합성 데이터" in md
    assert "| 예산 | 1,000만 원 |" in md
    md_path, json_path = save_plan(plan, tmp_path)
    assert md_path.read_text(encoding="utf-8") == md
    assert (
        FestivalPlan.model_validate_json(json_path.read_text(encoding="utf-8")).plan_id
        == plan.plan_id
    )
