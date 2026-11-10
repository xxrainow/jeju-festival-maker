import json

import pytest

from agent.llm import LLMError
from agent.request_parser import (
    MAX_TEXT_CHARS,
    SYSTEM_PROMPT,
    RequestParseError,
    build_request,
    jeju_areas,
    parse_krw,
    parse_request,
    resolve_region,
)

AREAS = jeju_areas()


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


@pytest.mark.parametrize(
    ("text", "krw"),
    [
        ("1천만 원", 10_000_000),
        ("천만원", 10_000_000),
        ("1,500만 원", 15_000_000),
        ("1억 5천만", 150_000_000),
        ("1.5억", 150_000_000),
        ("300000원", 300_000),
        ("삼백만 원", 3_000_000),
        ("3천5백만", 35_000_000),
        ("예산 약 2천만원 정도", 20_000_000),
        ("100만 원 이하", 1_000_000),
        ("많이", None),
        ("10달러", None),
        (None, None),
    ],
)
def test_parse_krw(text, krw):
    assert parse_krw(text) == krw


@pytest.mark.parametrize(
    ("text", "area"),
    [
        ("애월", "제주시 애월읍"),
        ("애월읍에서", "제주시 애월읍"),
        ("서귀포 표선", "서귀포시 표선면"),
        ("성산일출봉 근처", "서귀포시 성산읍"),
        ("노형동 일대", "제주시 노형동"),
        ("제주시 애월읍", "제주시 애월읍"),
    ],
)
def test_resolve_region(text, area):
    assert resolve_region(text, AREAS) == (area, None)


@pytest.mark.parametrize(
    ("text", "note"),
    [
        ("애월이나 한림", "여러 곳"),
        ("협재", "정하지 못했어요"),
        ("중앙로", "정하지 못했어요"),  # 도로 이름은 동으로 보지 않는다
        ("제주시", "제주 전역"),
    ],
)
def test_resolve_region_unclear(text, note):
    area, message = resolve_region(text, AREAS)
    assert area is None and note in message


def test_design_document_example():
    """기획서 9-1 예시: "애월에서 감귤로 상권 살리는 축제, 예산 1천만 원"."""
    fields = {
        "region_text": "애월",
        "purpose": "지역 상권 활성화",
        "interest": "감귤",
        "budget_text": "1천만 원",
        "season": None,
        "months": [],
        "target": None,
    }
    parsed = build_request(fields, AREAS)
    assert parsed.request.model_dump() == {
        "region": "제주시 애월읍",
        "purpose": "지역 상권 활성화",
        "interest": "감귤",
        "budget_max_krw": 10_000_000,
        "season": None,
        "target": None,
    }
    assert parsed.notes == []


def test_months_become_season_and_bad_values_are_dropped():
    parsed = build_request(
        {"months": [12, 1], "purpose": "축제 홍보", "season": "장마", "budget_text": "많이"}, AREAS
    )
    assert parsed.request.season == "겨울"
    assert parsed.request.purpose is None
    assert parsed.request.budget_max_krw is None
    notes = " ".join(parsed.notes)
    assert (
        "겨울로 봤어요" in notes
        and "선택지에 없어서" in notes
        and "금액으로 읽지 못했어요" in notes
    )
    mixed = build_request({"months": [4, 8]}, AREAS)
    assert mixed.request.season is None and "섞여" in mixed.notes[0]


def test_empty_fields_give_empty_request():
    parsed = build_request({"region_text": "null", "interest": "  ", "target": None}, AREAS)
    assert parsed.request.model_dump() == {
        "region": None,
        "purpose": None,
        "interest": None,
        "budget_max_krw": None,
        "season": None,
        "target": None,
    }


def test_parse_request_calls_llm_with_text_as_json():
    llm = FakeLLM(
        {"region_text": "표선", "interest": "해녀", "target": "20대 커플", "season": "여름"}
    )
    parsed = parse_request("표선에서 여름에 20대 커플 대상 해녀 축제", llm, areas=AREAS)
    assert parsed.request.region == "서귀포시 표선면"
    assert parsed.request.season == "여름"
    assert parsed.request.target == "20대 커플"
    system, user = llm.calls[0]
    assert system == SYSTEM_PROMPT and "<text>" in user and '"표선에서' in user


def test_parse_request_retries_on_bad_json_then_gives_up():
    llm = FakeLLM("아님", {"interest": "방어"})
    assert parse_request("방어 축제", llm, areas=AREAS).request.interest == "방어"
    assert "JSON 객체가 아니에요" in llm.calls[1][1]
    with pytest.raises(RequestParseError, match="직접 입력"):
        parse_request("방어 축제", FakeLLM("x", "[1, 2]"), areas=AREAS)


def test_parse_request_input_checks_and_llm_errors(monkeypatch):
    with pytest.raises(RequestParseError, match="한 문장"):
        parse_request("  ", FakeLLM())
    with pytest.raises(RequestParseError, match=f"{MAX_TEXT_CHARS}자"):
        parse_request("가" * (MAX_TEXT_CHARS + 1), FakeLLM())
    with pytest.raises(RequestParseError, match="시간 초과"):
        parse_request("감귤 축제", FakeLLM(LLMError("시간 초과")), areas=AREAS)
    monkeypatch.setattr("agent.proposals.default_llm", lambda: None)
    with pytest.raises(RequestParseError, match="AI 설정이 없어요"):
        parse_request("감귤 축제")
