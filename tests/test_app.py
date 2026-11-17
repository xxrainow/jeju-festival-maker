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
    assert lines[0][0] == "요즘 늘고 있는 축제예요 📈"
    assert lines[0][1] == (
        "2023년 이후 새로 생겨 2026년에 열리는 시장·상권 축제가 전국 16개예요. "
        "새로 생긴 축제 중 이 형식의 비율이 예전부터 열던 축제보다 3.6배 높아요."
    )
    assert lines[1][0] == "제주에는 아직 없어요"
    assert lines[2][0] == "관광객 관심은 아직 확인 중이에요"  # 데모 카드 관광객 관심은 pending
    assert lines[0][2] == "문화체육관광부 지역축제 개최계획 (2024~2026)"


JARGON = ["리프트", "신설", "확실한 상승", "관찰 대상", "성숙·감소", "정체", "선점 기회", "성공 사례",
          "검증할 가설", "소규모 버전", "중간값", "문체부", "pending", "lift", "verdict"]  # fmt: skip


PEOPLE_WORDS = ["관광객이에요", "%가 관광객", "명이 관광객", "사용 중", "사용자 중", "주민이"]


def test_jeju_tourist_share_matches_material_dictionary():
    assert screen.jeju_tourist_share() == 47.2  # A의 소재 사전 "전체 장소 관광 사용량 비중"


def card_texts(card) -> list[str]:
    texts = [t for line in screen.evidence_lines(card) for t in line]
    texts += [screen.reference_text(card), screen.timing_text(card), *screen.budget_lines(card)]
    return texts + [screen.check_phrase(h) for h in card.hypotheses]


def test_card_texts_have_no_jargon():
    cards = list(demo_proposal().ideas)
    ev = CARD.evidence
    for verdict, lift, count in [
        ("관찰 대상(신설 적음)", 1.4, 3),
        ("정체", 1.0, 5),
        ("성숙·감소", 0.6, 2),
    ]:
        trend = ev.trend.model_copy(
            update={"verdict": verdict, "new_lift": lift, "new_count": count}
        )
        jeju = ev.jeju_gap.model_copy(update={"jeju_count": 2})
        interest = ev.visitor_interest.model_copy(update={"value": 62.0, "status": "ready"})
        cards.append(CARD.model_copy(update={"evidence": ev.model_copy(
            update={"trend": trend, "jeju_gap": jeju, "visitor_interest": interest})}))  # fmt: skip
    titles = {screen.evidence_lines(c)[0][0] for c in cards}
    assert titles == {"요즘 늘고 있는 축제예요 📈", "조금씩 늘고 있는 축제예요",
                      "꾸준히 열리는 축제예요", "이미 많이 열리는 축제예요"}  # fmt: skip
    assert screen.evidence_lines(cards[-1])[1][0] == "제주에도 2개 있어요"
    title, body, _ = screen.evidence_lines(cards[-1])[2]
    assert title == "관광객이 많이 찾는 감귤이에요"  # 62% ≥ 제주 평균 47.2%
    assert body == "감귤 관련 제주 장소의 와이파이 사용량 중 관광 목적이 62%예요 (제주 평균 47%)."
    low = cards[-1].model_copy(update={"evidence": cards[-1].evidence.model_copy(update={
        "visitor_interest": cards[-1].evidence.visitor_interest.model_copy(update={"value": 30.0})})})  # fmt: skip
    assert screen.evidence_lines(low)[2][0] == "감귤 관련 장소는 관광보다 생활·업무 이용이 많아요"
    assert screen.evidence_lines(low, jeju_avg=25.0)[2][0] == "관광객이 많이 찾는 감귤이에요"
    assert screen.evidence_lines(low, jeju_avg=None)[2][1].endswith(
        "30%예요."
    )  # 평균을 모르면 비교 안 함
    assert "더 낮아요" in screen.evidence_lines(cards[-1])[0][1]  # 0.6배
    for c in cards:
        for text in card_texts(c):
            for word in JARGON:
                assert word not in text, (word, text)
            for word in PEOPLE_WORDS:  # 와이파이는 사용량이라 사람 수처럼 말하지 않는다
                assert word not in text, (word, text)


def test_card_other_fields_in_plain_words():
    cards = demo_proposal().ideas
    assert screen.reference_text(cards[0]) == "아직 전국에 대표 축제가 없어요. 먼저 시작할 기회예요"
    assert screen.reference_text(cards[1]) == "비슷한 성공 축제: 강릉커피축제, 김천김밥축제"
    assert screen.timing_text(cards[0]) == "추천 시기: 1월 · 이 달 제주 축제 0개"
    assert screen.budget_lines(cards[0])[0] == (
        "비슷한 축제는 보통 6,000만 원이 들어요. 입력한 1,000만 원으로는 작게 여는 걸 추천해요."
    )
    assert screen.budget_lines(cards[0])[-1] == "출처: 문화체육관광부 지역축제 개최계획 (2026)"


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("12월 애월읍 외지인 방문이 충분하다", "12월 애월읍 외지인 방문이 충분한지"),
        ("후보 장소 근처에 버스 접근성이 있다", "후보 장소 근처에 버스 접근성이 있는지"),
        ("관광객의 디저트·카페 소비가 많다", "관광객의 디저트·카페 소비가 많은지"),
        ("12월 추위·바람이 야외 체류를 막지 않는다", "12월 추위·바람이 야외 체류를 막지 않는지"),
        ("주민이 참여한다.", "주민이 참여하는지"),
        ("관광객이 온다", "관광객이 오는지"),
        ("값이 크다", "값이 큰지"),
        ("확인했음", "확인했음"),  # 규칙 밖은 그대로
    ],
)
def test_check_phrase(text, want):
    assert screen.check_phrase(text) == want


def test_season_conflict_and_demo_differences():
    from agent.draft_contracts import UserRequest

    seasons = {"감귤": [11, 12, 1]}
    summer = UserRequest(region="서귀포시 대정읍", interest="감귤", season="여름")
    assert screen.season_conflict(summer, seasons) == (
        "감귤은 11·12·1월이 제철이라 여름과 맞지 않아요. 계절이나 재료를 바꿔보세요."
    )
    assert screen.season_conflict(summer.model_copy(update={"season": "겨울"}), seasons) is None
    assert screen.season_conflict(summer.model_copy(update={"interest": "해녀"}), seasons) is None
    diffs = screen.demo_differences(demo_proposal(), summer.model_copy(update={"interest": "방어"}))
    assert diffs == [
        "지역: 입력 서귀포시 대정읍 · 카드 제주시 애월읍",
        "계절: 입력 여름 · 카드 1·12월",
        "재료: 입력 방어 · 카드 감귤",
    ]


def test_won():
    assert screen.won(10_000_000) == "1,000만 원"
    assert screen.won(278_000_000) == "2.78억 원"
    assert screen.won(None) == "미정"


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
    venue.evidence["night_return"] = {"hours": "21~23시", "is_synthetic": True, "data_label": "가상 데이터",
                                      "stops": [{"stop_name": "하모3리", "daily_boarding": 1.7}]}  # fmt: skip
    assert "야간 귀가(21~23시) 하루 승차: 하모3리 1.7명 [가상 데이터]" in screen.key_numbers(venue)
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

    # 데모 카드(애월 감귤, 추천 1월)가 시기 확인에서 실패하고 12월로 고쳐지는 조건
    at.selectbox[0].select("제주시 애월읍")
    at.selectbox[1].select("겨울")
    at.text_input[1].input("지역 상권 활성화")
    at.text_input[2].input("감귤")
    at.text_input[3].input("가족")
    at.checkbox[0].check()
    at.number_input[0].set_value(10_000_000)
    at.button[1].click().run()
    assert any("제주시 애월읍" in s for s in labels(at, "success"))

    next(b for b in at.button if b.label == "아이디어 카드 받기").click().run()
    assert any("데모 응답" in i for i in labels(at, "info"))  # notices
    assert len([h for h in at.subheader]) == 3

    next(b for b in at.button if b.label == "이 아이디어 고르기").click().run()
    assert not at.exception
    run = VerificationRun.model_validate(at.session_state["run"])
    assert len(run.rounds[-1].results) == 5
    assert len(at.dataframe) == 1  # 장소 후보 표

    shown = [m.value for m in at.markdown]
    assert any(v.startswith("**추천 시기: 1월 → 12월") for v in shown)  # 필드 이름 대신 쉬운 말
    assert not any("timing.recommended_months" in v for v in shown)
    assert any("timing.recommended_months" in c.value for c in at.code)  # 개발자용 원문은 접기 안에

    next(b for b in at.button if b.label == "이대로 진행").click().run()
    # agent/plan.py가 합쳐진 뒤로는 기획서 생성을 부르고, AI 설정이 없으면 안내 문장을 보여준다
    assert any("AI 설정이 없어요" in w for w in labels(at, "warning"))
    assert not at.exception


def _round(n, timing_status, timing_evidence, suggestion=None, changes=()):
    from agent.draft_contracts import CheckRound

    results = [
        CheckResult(
            check="check_timing",
            status=timing_status,
            reason="원문",
            evidence=timing_evidence,
            suggestion=suggestion,
        ),
        *[
            CheckResult(check=c, status="pass", reason="r")
            for c in ("check_venue", "check_target", "check_risk", "check_budget")
        ],
    ]
    return CheckRound(round=n, results=results, changes=list(changes))


def test_friendly_changes_use_plain_words():
    from agent.draft_contracts import IdeaChange, Suggestion

    why = "추천 월이 모두 확인을 통과하지 못해 … 재료 제철(11·12·1월) 안에서 골랐어요."
    sug = Suggestion(field="timing.recommended_months", value=[12], why=why)
    first = _round(1, "fail", {
        "low_months": [1],
        "material_season": {"months": [11, 12, 1], "basis": "기획서 7절 내부 근거"},
        "month_checks": [{"month": 1, "status": "fail", "outsider_visitors_index": 0.71, "good_weeks": [],
                          "bad_weeks": [{"week": "1월 2주차", "why": ["바람 1.8배, 9년 중 9년"]}]}],
    }, sug, [IdeaChange(field="timing.recommended_months", before=[1], after=[12], why=why)])  # fmt: skip
    second = _round(2, "conditional", {
        "slightly_low_months": [12], "material_season": {"months": [11, 12, 1], "basis": "x"},
        "month_checks": [{"month": 12, "status": "conditional"}],
    })  # fmt: skip
    card = CARD.model_copy(
        update={"timing": CARD.timing.model_copy(update={"recommended_months": [1]})}
    )
    final = card.model_copy(
        update={"timing": card.timing.model_copy(update={"recommended_months": [12]})}
    )
    run = VerificationRun(
        original=card, final=final, rounds=[first, second], outcome="ready_for_approval"
    )
    [ch] = screen.friendly_changes(run)
    assert ch["title"] == "추천 시기: 1월 → 12월"
    assert ch["reason"] == "1월은 관광객이 평소보다 적고 바람이 강한 주가 많아요."
    assert ch["note"] == "12월은 평소보다 관광객이 약간 적지만, 제철 안에서 가장 나은 달이에요."
    assert ch["season"] == "제철: 11·12·1월"
    assert ch["numbers"][0].startswith("1월 관광객 지표")  # 관광객이 실패 이유라 앞에
    assert ch["numbers"][1].startswith("1월 날씨 나쁜 주")
    shown = " ".join([ch["title"], ch["reason"], ch["note"], ch["season"], *ch["numbers"]])
    assert "기획서" not in shown and "timing." not in shown
    for word in ("fail", "pass", "conditional"):
        assert word not in shown


def test_reason_numbers_come_first_and_low_data_is_shown():
    """대정 12월처럼 날씨만 이유면 날씨 숫자가 앞, 관광객 지표는 뒤. 자료가 적으면 안내."""
    from agent.draft_contracts import IdeaChange, Suggestion

    why = "12월은 모든 주가 … 그 달을 빼요."
    sug = Suggestion(field="timing.recommended_months", value=[11], why=why)
    first = _round(1, "fail", {
        "low_months": [], "low_data": ["날씨 지점(제주)이 53km 떨어져 있어요"],
        "month_checks": [
            {"month": 11, "status": "pass", "outsider_visitors_index": 1.04, "good_weeks": [46], "bad_weeks": []},
            {"month": 12, "status": "fail", "outsider_visitors_index": 0.9, "good_weeks": [],
             "bad_weeks": [{"week": "12월 1주차", "why": ["바람 1.8배, 9년 중 9년"]}]},
        ],
    }, sug, [IdeaChange(field="timing.recommended_months", before=[11, 12], after=[11], why=why)])  # fmt: skip
    second = _round(2, "pass", {"month_checks": [{"month": 11, "status": "pass"}]})
    card = CARD.model_copy(
        update={"timing": CARD.timing.model_copy(update={"recommended_months": [11, 12]})}
    )
    final = card.model_copy(
        update={"timing": card.timing.model_copy(update={"recommended_months": [11]})}
    )
    run = VerificationRun(
        original=card, final=final, rounds=[first, second], outcome="ready_for_approval"
    )
    [ch] = screen.friendly_changes(run)
    assert ch["reason"] == "12월은 바람이 강한 주가 많아요."
    assert ch["numbers"][0].startswith("12월 날씨 나쁜 주 1/1주 (바람 1.8배")
    assert ch["numbers"][1].startswith("12월 관광객 지표 0.9")
    assert ch["low_data"] == ["날씨 지점(제주)이 53km 떨어져 있어요"]
    assert screen.low_data_notes(first.results) == ["날씨 지점(제주)이 53km 떨어져 있어요"]


def test_app_warns_summer_citrus_and_demo_cards(no_llm):
    """여름 + 감귤 입력: 계절-제철 안내와 데모 카드 경고 두 개, 카드 문장에 분석 용어 없음."""
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.selectbox[0].select("서귀포시 대정읍")
    at.selectbox[1].select("여름")
    at.text_input[2].input("감귤")
    at.button[1].click().run()
    warnings = labels(at, "warning")
    assert any("감귤은 11·12·1월이 제철이라 여름과 맞지 않아요" in w for w in warnings)
    next(b for b in at.button if b.label == "아이디어 카드 받기").click().run()
    warnings = labels(at, "warning")
    assert any("감귤은 11·12·1월이 제철이라" in w for w in warnings)
    demo = [w for w in warnings if screen.DEMO_WARNING in w]
    assert (
        demo
        and "계절: 입력 여름 · 카드 1·12월" in demo[0]
        and "지역: 입력 서귀포시 대정읍" in demo[0]
    )
    shown = " ".join([m.value for m in at.markdown] + [c.value for c in at.caption])
    for word in ("리프트", "신설", "확실한 상승", "선점 기회", "검증할 가설", "문체부 지역축제"):
        assert word not in shown, word
    assert "고르면 확인할 것" in shown


def test_interest_sentence_follows_basis():
    """관광 비중 기준이 '축제 동네'면 재료가 아니라 동네 기준이라고 쓴다 (예: 방어 → 대정읍)."""
    ev = CARD.evidence
    fest = ev.visitor_interest.model_copy(update={
        "value": 46.4, "status": "ready",
        "metric": "같은 재료 기존 축제가 열리는 동네의 관광 목적 사용량 비중(%)",
    })  # fmt: skip
    card = CARD.model_copy(update={"material": "방어",
                                   "evidence": ev.model_copy(update={"visitor_interest": fest})})  # fmt: skip
    title, body, _ = screen.evidence_lines(card, jeju_avg=47.2)[2]
    assert title == "방어 축제가 열리는 동네는 관광보다 생활·업무 이용이 많아요"
    assert body == (
        "방어 축제가 열리는 동네의 와이파이 사용량 중 관광 목적이 46%예요 (제주 평균 47%)."
        " 방어 자체가 아니라 동네 전체 기준이에요."
    )
    assert "관련 제주 장소" not in body
    high_title, _, _ = screen.evidence_lines(card, jeju_avg=40.0)[2]
    assert high_title == "방어 축제가 열리는 동네는 관광객이 많이 찾아요"
    place = ev.visitor_interest.model_copy(update={
        "value": 62.0, "status": "ready", "metric": "관련 장소 관광 목적 사용량 비중(%)",
    })  # fmt: skip
    card2 = CARD.model_copy(update={"evidence": ev.model_copy(update={"visitor_interest": place})})
    assert screen.evidence_lines(card2, jeju_avg=47.2)[2][1].startswith(
        "감귤 관련 제주 장소의 와이파이 사용량"
    )
