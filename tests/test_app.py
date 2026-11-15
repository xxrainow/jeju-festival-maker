from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent.demo_cards import demo_proposal
from agent.draft_contracts import CheckResult, VerificationRun
from app import screen

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
CARD = demo_proposal().ideas[0]


def test_evidence_lines_show_waiting_and_sources():
    lines = screen.evidence_lines(CARD)
    assert lines[0][0] == "요즘 뜨는 형식인가?"
    assert lines[2][1] == screen.WAITING  # 데모 카드 관광객 관심은 pending
    assert all(src for _, _, src in lines)


def test_won_and_budget_lines():
    assert screen.won(10_000_000) == "1,000만 원"
    assert screen.won(278_000_000) == "2.78억 원"
    assert screen.won(None) == "미정"
    assert any("출처" in line for line in screen.budget_lines(CARD))


def test_key_numbers_and_venue_table():
    venue = CheckResult(
        check="check_venue",
        status="pass",
        reason="r",
        evidence={
            "radius_m": 500,
            "low_usage_daily": 9.0,
            "candidate_places": [
                {"name": "산이물공원", "admin_area": "서귀포시 대정읍", "latitude": 33.2,
                 "longitude": 126.2, "tourism_share_pct": 96.0, "stop_name": "하모3리",
                 "stop_distance_m": 363, "stop_daily_users": 62.1},
            ],
        },
    )  # fmt: skip
    assert screen.venue_table(venue)[0]["가까운 정류소"] == "하모3리"
    assert "반경 500m" in screen.key_numbers(venue)[0]
    timing = CheckResult(
        check="check_timing", status="pass", reason="r",
        evidence={"outsider_visitors_index": {11: 1.04}, "recommended_weeks": ["11월 2주차"]},
    )  # fmt: skip
    assert screen.key_numbers(timing)[0] == "외지인 방문 지수(연평균 1): 11월 1.04"
    risk = CheckResult(check="check_risk", status="pass", reason="r",
                       evidence={"congestion": {"status": "pending"}})  # fmt: skip
    assert screen.key_numbers(risk) == ["정체: 데이터 대기"]


@pytest.fixture
def no_llm(monkeypatch):
    """.env에 키가 들어가도 테스트는 AI 없이 돈다."""
    monkeypatch.setenv("LLM_PROVIDER", "")
    monkeypatch.setenv("LLM_API_KEY", "")


def labels(at, kind):
    return [el.value for el in getattr(at, kind)]


def test_app_runs_from_sentence_to_approval_without_llm(no_llm):
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert any("admdongkor" in c.value for c in at.caption)  # 첫 화면에도 출처

    at.text_input[0].input("대정읍 방어 축제, 상권 활성화, 11~12월, 가족, 예산 1천만 원")
    at.button[0].click().run()
    assert any("AI 설정이 없어요" in w for w in labels(at, "warning"))

    at.selectbox[0].select("서귀포시 대정읍")
    at.selectbox[1].select("겨울")
    at.text_input[1].input("지역 상권 활성화")
    at.text_input[2].input("방어")
    at.text_input[3].input("가족")
    at.checkbox[0].check()
    at.number_input[0].set_value(10_000_000)
    at.button[1].click().run()
    assert any("서귀포시 대정읍" in s for s in labels(at, "success"))

    next(b for b in at.button if b.label == "아이디어 카드 받기").click().run()
    assert any("데모 응답" in i for i in labels(at, "info"))  # notices
    assert len([h for h in at.subheader]) == 3

    next(b for b in at.button if b.label == "이 아이디어 고르기").click().run()
    assert not at.exception
    run = VerificationRun.model_validate(at.session_state["run"])
    assert len(run.rounds[-1].results) == 5
    assert len(at.dataframe) == 1  # 장소 후보 표

    next(b for b in at.button if b.label == "이대로 진행").click().run()
    assert any("기획서 기능 준비 중" in i for i in labels(at, "info"))
    assert not at.exception
