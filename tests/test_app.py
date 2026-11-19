from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent.draft_contracts import CheckResult, VerificationRun
from app import screen
from tests.demo_helpers import december_demo  # noqa: F401 - 픽스처
from tests.demo_helpers import december_demo_proposal as demo_proposal

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
# 데모 카드 1은 시연용으로 1월이지만, 이 파일의 화면 테스트는 원래 12월 카드 기준이다
pytestmark = pytest.mark.usefixtures("december_demo")
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
    assert screen.timing_text(cards[0]) == "추천 시기: 12월 · 이 달 제주 축제 1개"
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
        "계절: 입력 여름 · 카드 12월",
        "재료: 입력 방어 · 카드 감귤",
    ]


def test_md_escapes_tildes_for_markdown():
    """ "~"가 두 번 나오면 Streamlit 마크다운이 취소선으로 바꾸므로 화면 출력 전에 이스케이프한다."""
    text = "추천 주: 1월 1주차 (1/1~1/7), 6월 1주차 (6/4~6/10)"
    escaped = screen.md(text)
    assert escaped == r"추천 주: 1월 1주차 (1/1\~1/7), 6월 1주차 (6/4\~6/10)"
    assert screen.md(escaped) == escaped  # 두 번 불러도 겹쳐 바꾸지 않음
    assert screen.md(None) is None and screen.md(3) == 3
    assert screen.md("물결 없음") == "물결 없음"


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
    assert "야간 귀가(21~23시) 하루 승차: 하모3리 1.7명 (가상 데이터)" in screen.key_numbers(venue)
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


def click(at, label: str) -> AppTest:
    next(b for b in at.button if b.label == label).click().run()
    return at


def pick(at, index=0) -> AppTest:
    [b for b in at.button if b.label == "자세히 보기"][index].click().run()
    click(at, "이 아이디어 고르기")
    return at


def choose(at, name: str) -> AppTest:
    next(r for r in at.radio if r.label == "진행할 안").set_value(name).run()
    return at


def labels(at, kind):
    return [el.value for el in getattr(at, kind)]


def test_app_runs_from_sentence_to_approval_without_llm(no_llm):
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert any("admdongkor" in c.value for c in at.caption)  # 첫 화면에도 출처

    at.text_input[0].input("대정읍 방어 축제, 상권 활성화, 11~12월, 가족, 예산 1천만 원")
    click(at, "문장으로 조건 정리하기")
    assert any("AI 설정이 없어요" in w for w in labels(at, "warning"))

    at.selectbox[0].select("서귀포시 대정읍")
    at.selectbox[1].select("겨울")
    at.text_input[1].input("지역 상권 활성화")
    at.text_input[2].input("방어")
    at.text_input[3].input("가족")
    at.number_input[0].set_value(10_000_000)
    click(at, "아이디어 보기")
    assert at.session_state["request"]["region"] == "서귀포시 대정읍"
    notice = next(e for e in at.expander if e.label == "예시 카드예요")
    assert any("데모 응답" in m.value for m in notice.markdown)  # notices는 접는 안내에 보존
    assert len([h for h in at.subheader]) == 3

    pick(at)
    assert not at.exception
    run = VerificationRun.model_validate(at.session_state["run"])
    assert len(run.rounds[-1].results) == 5
    assert len(at.dataframe) == 1  # 장소 후보 표

    shown = [m.value for m in at.markdown]
    # 입력 계절이 겨울이라 제철(11·12·1월) 중 겨울인 1월을 먼저 고른다 (11월은 가을)
    assert any(v.startswith("**추천 시기: 12월 → 1월") for v in shown)  # 필드 이름 대신 쉬운 말
    assert not any("timing.recommended_months" in v for v in shown)
    assert not at.code  # 개발자용 원문은 화면에 없음
    # 확인 결과 요약 줄·회차 설명은 화면에서 뺐다 (카드와 "바뀐 점"에 같은 내용이 있음)
    assert not any("다시 확인했어요" in c.value for c in at.caption)

    # 화면 문장에는 이스케이프 안 된 "~"가 없다 (추천 주, 출처 기간 등). 표 값은 그대로
    import re

    texts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    texts += labels(at, "warning") + labels(at, "info") + labels(at, "success")
    assert any(r"\~" in t for t in texts)
    assert not [t for t in texts if re.search(r"(?<!\\)~", t)]
    table = at.dataframe[0].value
    assert not table.astype(str).apply(lambda col: col.str.contains("\\", regex=False)).any().any()

    next(b for b in at.button if b.label == "이대로 진행").click().run()
    # 기획서 생성을 부르고, AI 설정이 없으면 쉬운 이유 한 줄 + 다시 만들기
    assert "AI 설정이 없어 기획서를 만들 수 없어요." in labels(at, "warning")
    assert any(b.label == screen.RETRY_PLAN_LABEL for b in at.button)
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


def test_near_festival_month_reason_place_and_distance():
    """대정 11·12월: 11월은 같은 동네 방어 축제, 12월은 바람 → 바뀐 점에 두 이유 모두 (QA 보고서 2번)."""
    from agent.draft_contracts import IdeaChange, Suggestion

    near = {"name": "제26회 최남단 방어 축제", "admin_area": "서귀포시 대정읍",
            "relation": "같은 동네", "distance_km": 0.0}  # fmt: skip
    why = "11월에는 … 12월은 … 그 달을 빼요."
    sug = Suggestion(field="timing.recommended_months", value=[1], why=why)
    first = _round(1, "fail", {
        "low_months": [],
        "overlapping_festivals": [near | {"month": 11, "months": [11]}],
        "month_checks": [
            {"month": 11, "status": "fail", "outsider_visitors_index": 1.04, "good_weeks": ["11월 2주차"],
             "bad_weeks": [], "near_festivals": [near], "near_downgraded": False},
            {"month": 12, "status": "fail", "outsider_visitors_index": 0.9, "good_weeks": [],
             "bad_weeks": [{"week": "12월 1주차", "why": ["바람 1.8배, 9년 중 9년"]}]},
        ],
    }, sug, [IdeaChange(field="timing.recommended_months", before=[11, 12], after=[1], why=why)])  # fmt: skip
    second = _round(2, "pass", {"month_checks": [{"month": 1, "status": "pass"}]})
    card = CARD.model_copy(
        update={"timing": CARD.timing.model_copy(update={"recommended_months": [11, 12]})}
    )
    final = card.model_copy(
        update={"timing": card.timing.model_copy(update={"recommended_months": [1]})}
    )
    run = VerificationRun(
        original=card, final=final, rounds=[first, second], outcome="ready_for_approval"
    )
    [ch] = screen.friendly_changes(run)
    assert ch["reason"] == (
        "11월에는 같은 동네(서귀포시 대정읍)에서 같은 재료 축제(제26회 최남단 방어 축제)가 열려요. "
        "12월은 바람이 강한 주가 많아요."
    )
    assert "같은 재료 축제: 제26회 최남단 방어 축제(11월, 서귀포시 대정읍, 같은 동네)" in (
        screen.key_numbers(first.results[0])
    )
    # 가까운 동네(10km 이내)는 거리, 장소를 모르면 "장소 미확인"
    seohong = {"name": "서홍동 벚꽃구경", "admin_area": "서귀포시 서홍동",
               "relation": "가까운 동네", "distance_km": 6.1, "month": 4}  # fmt: skip
    assert screen.near_festival_sentence(4, [seohong]) == (
        "4월에는 약 6.1km 떨어진 서귀포시 서홍동에서 같은 재료 축제(서홍동 벚꽃구경)가 열려요."
    )
    unknown = {"name": "어느 축제", "admin_area": None, "relation": "장소 미확인",
               "distance_km": None, "month": 3}  # fmt: skip
    assert screen.festivals_text([seohong, unknown]) == (
        "서홍동 벚꽃구경(4월, 서귀포시 서홍동, 약 6.1km), 어느 축제(3월, 장소 미확인)"
    )


def test_months_are_shown_in_continuous_order():
    assert screen.months_text([1, 2, 11, 12]) == "11·12·1·2월"
    assert screen.months_text([12, 1, 2]) == "12·1·2월"
    assert screen.months_text([3, 4, 5]) == "3·4·5월"
    assert screen.months_text([9, 11]) == "9·11월"
    assert screen.months_text([1]) == "1월"


def test_season_outside_notice_in_changes_and_result():
    """에이전트가 입력 계절 밖 달로 바꾸면 바뀐 점과 시기 결과에 안내 (QA 2차 #8·#12)."""
    from agent.draft_contracts import IdeaChange, Suggestion

    sentence = "입력한 계절(겨울)에는 맞는 달이 없어 5월로 바꿨어요."
    why = "추천 월이 모두 … 5월(1.77)로 바꿔요. " + sentence
    sug = Suggestion(field="timing.recommended_months", value=[5], why=why)
    first = _round(1, "fail", {
        "low_months": [12, 1, 2], "season_outside_suggestion": sentence,
        "month_checks": [{"month": m, "status": "fail", "outsider_visitors_index": 0.5,
                          "good_weeks": ["w"], "bad_weeks": []} for m in (12, 1, 2)],
    }, sug, [IdeaChange(field="timing.recommended_months", before=[12, 1, 2], after=[5], why=why)])  # fmt: skip
    second = _round(2, "pass", {"month_checks": [{"month": 5, "status": "pass"}]})
    card = CARD.model_copy(
        update={"timing": CARD.timing.model_copy(update={"recommended_months": [12, 1, 2]})}
    )
    final = card.model_copy(
        update={"timing": card.timing.model_copy(update={"recommended_months": [5]})}
    )
    run = VerificationRun(
        original=card, final=final, rounds=[first, second], outcome="ready_for_approval"
    )
    [ch] = screen.friendly_changes(run)
    assert ch["title"] == "추천 시기: 12·1·2월 → 5월" and ch["note"] == sentence
    assert screen.season_notice(run) == sentence
    # 고치지 않은 안(직접 고친 안 등)에는 안내 없음
    plain = VerificationRun(
        original=final, final=final, rounds=[second], outcome="ready_for_approval"
    )
    assert screen.season_notice(plain) is None


def test_synthetic_labels_are_unified():
    """화면 표시는 모두 "(가상 데이터)" (가짜 데이터, [가상 데이터] 없음)."""
    from analytics.flow_source import SYNTHETIC_WARNING, FlowData

    risk = CheckResult(check="check_risk", status="conditional", reason="r", evidence={
        "residential": {"is_synthetic": True, "areas": [{"admin_area": "제주시 애월읍", "ratio": 1.1}]},
        "congestion": {"links_checked": 3, "min_ratio": 0.9, "is_synthetic": True},
    })  # fmt: skip
    lines = screen.key_numbers(risk)
    assert all(line.endswith("(가상 데이터)") for line in lines)
    assert "가짜" not in SYNTHETIC_WARNING
    flow = FlowData(data=None, is_synthetic=True, path=None, period=("2025-05-12", "2025-05-25"))
    assert flow.label.endswith("2025-05-12~2025-05-25 (가상 데이터)")
    assert "[가상" not in " ".join(lines)


def test_app_warns_summer_citrus_and_demo_cards(no_llm):
    """계절 충돌은 경고로, 예시 카드 설명은 접힌 안내에 보존한다."""
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.selectbox[0].select("서귀포시 대정읍")
    at.selectbox[1].select("여름")
    at.text_input[2].input("감귤")
    click(at, "아이디어 보기")
    warnings = labels(at, "warning")
    assert any(
        "감귤은 11·12·1월이 제철이라 여름과 맞지 않아요" in w for w in warnings
    )  # 입력한 조건의 충돌 안내도 카드 화면에 유지
    assert any(e.label == "예시 카드예요" for e in at.expander)
    demo = [m.value for m in at.markdown if screen.DEMO_WARNING in m.value]
    assert demo and f"이유: {screen.NO_KEY_REASON}" in demo[0]  # 예시 카드로 바뀐 이유
    assert (
        demo
        and "계절: 입력 여름 · 카드 12월" in demo[0]
        and "지역: 입력 서귀포시 대정읍" in demo[0]
    )
    shown = " ".join([m.value for m in at.markdown] + [c.value for c in at.caption])
    for word in ("리프트", "신설", "확실한 상승", "선점 기회", "검증할 가설", "문체부 지역축제"):
        assert word not in shown, word
    assert "고르면 확인할 것" in shown


# ---------- 예산 입력, 직접 고쳐서 다시 확인 ----------


def confirm(region="서귀포시 대정읍", budget=None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.selectbox[0].select(region)
    if budget is not None:
        at.number_input[0].set_value(budget)
    return at


def test_budget_blank_is_undecided_and_number_is_used(no_llm):
    from agent.draft_contracts import UserRequest

    at = confirm()
    assert at.number_input[0].value is None  # 처음엔 빈칸
    click(at, "아이디어 보기")
    assert UserRequest.model_validate(at.session_state["request"]).budget_max_krw is None
    at = confirm(budget=10_000_000)
    click(at, "아이디어 보기")
    assert UserRequest.model_validate(at.session_state["request"]).budget_max_krw == 10_000_000


def to_results(region="서귀포시 대정읍") -> AppTest:
    at = confirm(region)
    click(at, "아이디어 보기")
    pick(at)
    assert at.session_state["step"] == 3
    return at


def recheck(at, months, place=None, scale=None) -> AppTest:
    at.multiselect[0].set_value(months)
    if place:
        next(s for s in at.selectbox if s.label.startswith("장소")).select(place)
    if scale:
        at.radio[0].set_value(scale)
    next(b for b in at.button if b.label == "이 조건으로 다시 확인").click().run()
    return at


def test_manual_months_are_checked_as_is_without_auto_fix(no_llm):
    at = to_results()
    agent = VerificationRun.model_validate(at.session_state["run"])
    assert agent.final.timing.recommended_months == [11]  # 에이전트는 12월 → 11월로 고침
    assert at.multiselect[0].value == [11]  # 처음 값은 지금 카드 값
    at = recheck(at, [12])
    manual = VerificationRun.model_validate(at.session_state["manual_run"])
    assert len(manual.rounds) == 1 and not manual.rounds[0].changes  # 자동 수정 없음
    assert manual.final.timing.recommended_months == [12]
    assert manual.rounds[0].results[0].status == "fail"
    assert [t.label for t in at.tabs] == ["에이전트 추천안", "내가 고친 안"]
    assert not at.exception


def test_failing_manual_plan_blocks_progress(no_llm):
    at = recheck(to_results(), [12])
    choose(at, "내가 고친 안")
    button = next(b for b in at.button if b.label == "이대로 진행")
    assert button.disabled
    blocked = [w for w in at.warning if "시기 확인을 통과하지 못해 진행을 멈췄어요" in w.value]
    assert blocked and blocked[0].icon == "❌"  # Streamlit은 앞의 이모지를 아이콘으로 보여준다
    assert any("이렇게 바꿔보세요" in m.value and "11월" in m.value for m in at.markdown)


def test_check_cards_use_combined_details_and_keep_evidence(no_llm):
    at = to_results()
    details = [
        e for e in at.expander
        if e.label == "상세 결과와 근거 보기" or e.label.startswith("장소 후보 ")
    ]
    assert len(details) == 5
    assert not any(e.label == "주의할 점" for e in at.expander)
    # 장소 카드는 펼침 문구에 후보 개수를 보여준다 (표 행 수와 같게)
    venue_rows = len(details[1].dataframe[0].value)
    assert details[1].label == f"장소 후보 {venue_rows}곳 비교·근거 보기"
    assert len(details[1].dataframe) == 1  # 장소 후보는 통합 상세 안에 보존
    assert any(c.value.startswith("출처:") for c in details[1].caption)
    assert any("반경 500m" in c.value for c in details[1].caption)
    assert not at.exception


def test_check_card_primary_metric_preserves_pending_and_synthetic():
    pending = CheckResult(check="check_target", status="pending", reason="대상 미입력")
    assert screen.check_card_summary(pending)["value"] == screen.WAITING
    risk = CheckResult(
        check="check_risk", status="conditional", reason="소음 주의",
        evidence={"residential": {"areas": [{"admin_area": "애월읍", "ratio": 1.63}],
                                  "is_synthetic": True}},
    )
    summary = screen.check_card_summary(risk)
    assert summary["value"] == "1.63배" and summary["synthetic"]


def test_blocked_month_guidance_explains_data_and_preserves_other_months():
    from agent.demo_cards import DEMO_REQUEST, demo_proposal
    from agent.verify import verify_idea
    from analytics.real_checks import REAL_TOOLS

    card = demo_proposal().ideas[0]
    edited = screen.edited_card(card, [1, 11], None, "소규모 버전")
    run = verify_idea(edited, DEMO_REQUEST, REAL_TOOLS, max_fixes=0)
    text = " ".join(screen.blocked_check_guidance(run))
    assert "1월 약 71%" in text and "80% 미만" in text
    assert "실제 관광객 수나 개최 금지" in text
    assert "선택한 1월이 통과하지 못해" in text
    assert "개최 월을 11월로 바꾸고" in text
    assert run.final.timing.recommended_months == [1, 11]


class FakePlanLLM:
    def complete_json(self, system, user):
        import json

        return json.dumps(
            {
                "background": "대정읍 상권에 손님을 모으는 작은 마켓을 제안한다.",
                "concept": "지역 가게와 농가가 함께 여는 주말 마켓이다.",
                "programs": [
                    {"name": "직거래 장터", "description": "농가가 직접 파는 장터"},
                    {"name": "가족 체험 부스", "description": "아이와 함께하는 만들기 체험"},
                ],
                "promotion": "마을 게시판과 SNS를 함께 쓴다.",
                "operation": "장소와 인력은 미확인이다.",
                "risk": "같은 재료 축제와 날짜를 겹치지 않게 잡는다.",
                "expected": "지역 가게에 손님이 늘 것으로 보인다.",
                "assumptions": ["참여할 가게를 모을 수 있다"],
            },
            ensure_ascii=False,
        )


def test_passing_manual_plan_makes_plan_from_it(no_llm, monkeypatch, tmp_path):
    import agent.plan
    import agent.proposals
    from agent.draft_contracts import FestivalPlan

    monkeypatch.setattr(agent.proposals, "default_llm", lambda: FakePlanLLM())
    monkeypatch.setattr(
        agent.plan, "save_plan", lambda plan: (tmp_path / "p.md", tmp_path / "p.json")
    )
    at = recheck(to_results(), [11], place="산이물공원", scale="작게")
    manual = VerificationRun.model_validate(at.session_state["manual_run"])
    assert manual.outcome == "ready_for_approval"
    assert manual.final.venue[0].name == "산이물공원" and manual.final.budget.scale == "소규모 버전"
    choose(at, "내가 고친 안")
    button = next(b for b in at.button if b.label == "이대로 진행")
    assert not button.disabled
    button.click().run()
    assert not at.exception
    plan = FestivalPlan.model_validate(at.session_state["plan"])
    assert plan.idea.venue[0].name == "산이물공원"
    assert plan.idea.timing.recommended_months == [11]
    assert any("내가 고친 안으로 기획서를 만들었어요" in str(el.value) for el in at.get("html"))


class FlakyPlanLLM(FakePlanLLM):
    """첫 응답은 정하지 않은 장소를 확정처럼 쓰고(두 번 시도 모두), 그다음부터는 규칙대로."""

    calls = 0

    def complete_json(self, system, user):
        import json

        FlakyPlanLLM.calls += 1
        data = json.loads(super().complete_json(system, user))
        if FlakyPlanLLM.calls <= 2:
            data["operation"] = "행사 장소는 산이물공원이다."
        return json.dumps(data, ensure_ascii=False)


def test_plan_failure_shows_plain_reason_and_retry(no_llm, monkeypatch, tmp_path):
    """④ 기획서 생성이 실패하면 쉬운 이유 한 줄 + "다시 만들기" (QA 2차 #18)."""
    import agent.plan
    import agent.proposals

    FlakyPlanLLM.calls = 0
    monkeypatch.setattr(agent.proposals, "default_llm", lambda: FlakyPlanLLM())
    monkeypatch.setattr(
        agent.plan, "save_plan", lambda plan: (tmp_path / "p.md", tmp_path / "p.json")
    )
    at = click(to_results(), "이대로 진행")
    assert at.session_state["step"] == 4 and "plan" not in at.session_state
    reason = "AI가 정하지 않은 장소를 정한 것처럼 써서 기획서를 쓰지 않았어요. 다시 만들어 보세요."
    assert reason in labels(at, "warning")
    assert not any("PlanResponseError" in w or "마지막 문제" in w for w in labels(at, "warning"))
    # 다른 곳을 눌러 다시 그려져도 저절로 다시 부르지 않는다
    calls = FlakyPlanLLM.calls
    at.run()
    assert FlakyPlanLLM.calls == calls and reason in labels(at, "warning")
    at = click(at, screen.RETRY_PLAN_LABEL)
    assert "plan" in at.session_state and "plan_error" not in at.session_state
    assert reason not in labels(at, "warning") and not at.exception


def test_plan_failure_reasons_are_plain():
    from agent.llm import LLMError
    from agent.plan import PlanGenerationError

    quota = PlanGenerationError("기획서 작성 중 AI 호출에 실패했어요. (HTTP 429)")
    quota.__cause__ = LLMError("무료 사용 한도를 넘었어요. (HTTP 429)")
    assert "사용 한도" in screen.plan_failure_reason(quota)
    down = PlanGenerationError("기획서 작성 중 AI 호출에 실패했어요.")
    down.__cause__ = LLMError("AI 응답이 너무 오래 걸려요.")
    assert screen.plan_failure_reason(down).startswith("AI 서버에 연결하지 못했어요")
    numbers = PlanGenerationError(
        "AI 응답이 규칙에 맞지 않아 기획서를 만들지 못했어요 (2회 시도). 마지막 문제: 입력에 없는 숫자를 썼어요: 7"
    )
    assert "근거에 없는 숫자" in screen.plan_failure_reason(numbers)
    other = PlanGenerationError("AI 응답이 규칙에 맞지 않아 … 마지막 문제: 응답이 JSON이 아니에요.")
    assert (
        screen.plan_failure_reason(other)
        == "AI가 쓴 기획서가 형식에 맞지 않았어요. 다시 만들어 보세요."
    )


def test_old_plan_is_cleared_when_choice_or_recheck_changes(no_llm, monkeypatch, tmp_path):
    import agent.plan
    import agent.proposals

    monkeypatch.setattr(agent.proposals, "default_llm", lambda: FakePlanLLM())
    monkeypatch.setattr(
        agent.plan, "save_plan", lambda plan: (tmp_path / "p.md", tmp_path / "p.json")
    )
    at = recheck(to_results(), [11])
    # 직접 고쳐서 다시 확인하면 그 안(내가 고친 안)이 바로 선택된다
    assert next(r for r in at.radio if r.label == "진행할 안").value == "내가 고친 안"
    choose(at, "에이전트 추천안")
    click(at, "이대로 진행")
    assert at.session_state["step"] == 4 and "plan" in at.session_state
    # ③으로 돌아가 진행할 안을 바꾸면 예전 기획서가 사라진다
    at.button(key=f"nav_{at.session_state['step'] - 1}").click().run()
    choose(at, "내가 고친 안")
    assert "plan" not in at.session_state and "approved" not in at.session_state
    assert not any("기획서를 만들었어요" in s for s in labels(at, "success"))
    # 고친 안으로 만든 뒤 돌아와서 다시 확인해도 사라진다
    click(at, "이대로 진행")
    assert "plan" in at.session_state
    at.button(key=f"nav_{at.session_state['step'] - 1}").click().run()
    at = recheck(at, [11, 12])
    assert "plan" not in at.session_state and "approved" not in at.session_state


def test_check_history_is_plain_words(no_llm):
    import re

    at = to_results()
    # 확인 과정은 "바뀐 점"과 한 타임라인으로 합쳤다 (따로 펼치는 칸 없음)
    assert not any(e.label == "확인 과정 자세히 보기" for e in at.expander)
    run = VerificationRun.model_validate(at.session_state["run"])
    rows = [screen.round_status_row(rd) for rd in run.rounds]
    assert rows[0]["label"] == "처음 확인" and rows[0]["items"][0] == ("시기", "fail")
    from app import style

    html = style.round_row_html(rows[-1], last=True)
    assert "지금 결과" in html and "실패" not in html
    for row in rows:
        assert not re.search(r"[A-Za-z_]{3,}", row["label"] + "".join(n for n, _ in row["items"]))


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


def test_promo_needs_final_approval_on_screen(no_llm, monkeypatch, tmp_path):
    import agent.plan
    import agent.proposals
    from app import promo

    monkeypatch.setattr(agent.proposals, "default_llm", lambda: FakePlanLLM())
    monkeypatch.setattr(
        agent.plan, "save_plan", lambda plan: (tmp_path / "p.md", tmp_path / "p.json")
    )
    monkeypatch.setattr(promo, "OUTPUT_DIR", tmp_path / "promo")
    at = to_results()
    click(at, "이대로 진행")
    assert at.session_state["step"] == 4
    assert not any(b.label == "홍보물 만들기" for b in at.button)  # 승인 전에는 ⑤에 못 감
    at.session_state["step"] = 5
    at.run()
    assert at.session_state["step"] == 4  # 억지로 넘겨도 ④로 돌아온다
    click(at, "기획서 최종 승인")
    assert at.session_state["step"] == 5
    from agent.draft_contracts import FestivalPlan

    assert FestivalPlan.model_validate(at.session_state["plan"]).status == "approved"
    make = next(b for b in at.button if b.label == "홍보물 만들기")
    assert not make.disabled
    make.click().run()
    assert not at.exception
    result = promo.PromoResult.model_validate(at.session_state["promo"])
    assert Path(result.poster_path).exists() and not result.used_ai_image
    assert any("기본 포스터" in w for w in labels(at, "warning"))  # 키 없음 안내
    assert any(
        c.value == "\n".join(result.poster_lines.values()) for c in at.code
    )  # 포스터 문구 6줄
    # 저장: 포스터·SNS 문구는 outputs/promo에, ZIP은 내려받기 버튼 (AI 없음이라 SNS 글은 없음)
    assert any(b.label == "기획서와 함께 ZIP으로 저장" for b in at.get("download_button"))
    click(at, "＋ 포스터 · SNS 문구 저장")
    assert any(result.poster_path in s for s in labels(at, "success"))
    # ③으로 돌아가서 같은 안이면 그대로, 다시 확인하면 홍보물도 지워진다
    at.button(key=f"nav_{at.session_state['step'] - 1}").click().run()
    at.button(key=f"nav_{at.session_state['step'] - 1}").click().run()
    assert at.session_state["step"] == 3
    choose(at, "에이전트 추천안")
    assert "promo" in at.session_state
    at = recheck(at, [11, 12])
    assert "promo" not in at.session_state and "plan" not in at.session_state


# ---------- 단계별 화면 ----------


def test_progress_and_summary_texts():
    from agent.draft_contracts import UserRequest

    assert (
        screen.progress_text(2)
        == "① 조건 입력 → **② 아이디어** → ③ 데이터로 확인 → ④ 기획서 → ⑤ 홍보물"
    )
    req = UserRequest(
        region="서귀포시 대정읍", season="겨울", interest="방어", budget_max_krw=10_000_000
    )
    assert screen.selection_summary(req) == "서귀포시 대정읍 · 겨울 · 방어 · 예산 1,000만 원"
    assert screen.selection_summary(req, CARD).endswith(f"/ 고른 아이디어: {CARD.title}")


def test_ai_failure_reason_by_cause():
    from agent.idea_cards import CardGenerationError
    from agent.llm import LLMError

    def wrapped(msg):
        try:
            try:
                raise LLMError(msg)
            except LLMError as cause:
                raise CardGenerationError(
                    f"아이디어 생성 중 AI 호출에 실패했어요. {cause}"
                ) from cause
        except CardGenerationError as e:
            return e

    assert (
        screen.ai_failure_reason(wrapped("무료 사용 한도를 넘었어요. (HTTP 429)"))
        == screen.QUOTA_REASON
    )
    for network in ("AI 응답이 너무 오래 걸려요.", "AI 서버 오류예요. (HTTP 503)"):
        assert screen.ai_failure_reason(wrapped(network)) == screen.CALL_FAIL_REASON
    # 키·모델 설정 오류는 예시 카드로 넘어가지 않고 원래 안내 (① 조건 입력)
    assert screen.ai_failure_reason(wrapped("API 키가 올바르지 않아요. (HTTP 401)")) is None
    rejected = CardGenerationError(
        "AI 응답이 형식에 맞지 않아 아이디어를 만들지 못했어요 (2회 시도). 마지막 문제: …"
    )
    assert screen.ai_failure_reason(rejected) is None and screen.cards_rejected(rejected)
    assert (
        screen.ai_failure_reason(CardGenerationError("AI 설정이 없어요. .env에 …"))
        == screen.NO_KEY_REASON
    )
    assert (
        screen.ai_failure_reason(CardGenerationError("조건에 맞는 형식이 3개보다 적어요.")) is None
    )


def test_steps_move_forward_and_back(no_llm):
    at = confirm()
    assert at.session_state["step"] == 1
    assert "**① 조건 입력**" in at.markdown[1].value
    click(at, "아이디어 보기")
    assert at.session_state["step"] == 2 and "**② 아이디어**" in at.markdown[1].value
    assert any(c.value == "서귀포시 대정읍 · 계절 미정 · 소재 미정 · 예산 미정" for c in at.caption)
    first = at.session_state["proposal"]
    # 완료한 조건 입력 탭으로 이동해도 기존 카드와 조건은 유지된다
    assert at.button(key="back_2").label == "조건 수정"
    assert not at.button(key="nav_1").disabled
    assert all(at.button(key=f"nav_{i}").disabled for i in range(2, 6))
    at.button(key="nav_1").click().run()
    assert at.session_state["step"] == 1 and at.session_state["proposal"] == first
    click(at, "아이디어 보기")
    assert at.session_state["step"] == 2
    # 아이디어 고르기 → ③, 돌아가서 같은 아이디어를 고르면 확인 결과 유지
    pick(at)
    assert at.session_state["step"] == 3 and "run" in at.session_state
    assert not any(b.label.startswith("←") for b in at.button)
    title = demo_proposal().ideas[0].title  # 예시 카드 첫 장
    assert any(c.value.endswith(f"/ 고른 아이디어: {title}") for c in at.caption)
    run = at.session_state["run"]
    at.button(key=f"nav_{at.session_state['step'] - 1}").click().run()
    pick(at)
    assert at.session_state["run"] == run
    # 다른 아이디어를 고르면 확인 결과부터 다시
    at.button(key=f"nav_{at.session_state['step'] - 1}").click().run()
    pick(at, 1)
    assert at.session_state["run"] != run
    # ①로 돌아가 조건을 바꾸면 뒤 단계 결과가 지워진다
    at.button(key=f"nav_{at.session_state['step'] - 1}").click().run()
    at.button(key=f"nav_{at.session_state['step'] - 1}").click().run()
    assert at.session_state["step"] == 1
    at.selectbox[0].select("제주시 애월읍")
    click(at, "아이디어 보기")
    assert at.session_state["request"]["region"] == "제주시 애월읍"
    for key in ("selected", "run"):
        assert key not in at.session_state
    assert not at.exception


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        (
            "무료 사용 한도를 넘었거나 요청이 너무 많아요. (HTTP 429)",
            "오늘 AI 사용 한도를 넘었어요",
        ),
        ("AI 서버에 연결하지 못했어요. 인터넷 연결을 확인해주세요.", "AI 서버에 연결하지 못했어요"),
        (
            "AI 서버 오류예요. 잠시 뒤에 다시 시도해주세요. (HTTP 503)",
            "AI 서버에 연결하지 못했어요",
        ),
    ],
)
def test_demo_cards_show_reason_on_ai_failure(monkeypatch, message, reason):
    import agent.proposals
    from agent.idea_cards import CardGenerationError
    from agent.llm import LLMError

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")
    real = agent.proposals.propose_idea_cards

    def failing(request, *, demo=True, **kw):
        if demo:
            return real(request, demo=True)
        try:
            raise LLMError(message)
        except LLMError as cause:
            raise CardGenerationError(f"아이디어 생성 중 AI 호출에 실패했어요. {cause}") from cause

    monkeypatch.setattr(agent.proposals, "propose_idea_cards", failing)
    at = click(confirm(), "아이디어 보기")
    assert at.session_state["step"] == 2
    demo = [m.value for m in at.markdown if screen.DEMO_WARNING in m.value]
    assert demo and reason in demo[0]
    assert "HTTP" not in demo[0] and "test-key" not in demo[0]  # 오류 원문·키는 보여주지 않음


def test_rejected_cards_show_retry_not_demo(monkeypatch):
    """AI 카드가 규칙 검사에 걸리면 예시 카드 대신 ①에서 "다시 받기" (QA 보고서 1번)."""
    import agent.proposals
    from agent.idea_cards import CardGenerationError

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")
    real = agent.proposals.propose_idea_cards
    calls = []

    def flaky(request, *, demo=True, **kw):
        calls.append(demo)
        if demo:
            raise AssertionError("예시 카드로 넘어가면 안 돼요")
        if len(calls) == 1:
            raise CardGenerationError(
                "AI 응답이 형식에 맞지 않아 아이디어를 만들지 못했어요 (2회 시도). "
                "마지막 문제: 후보를 3개가 아니라 2개 골랐어요."
            )
        return real(request, demo=True)  # 두 번째는 성공했다고 치고 카드 3장

    monkeypatch.setattr(agent.proposals, "propose_idea_cards", flaky)
    at = click(confirm(), "아이디어 보기")
    assert at.session_state["step"] == 1 and "proposal" not in at.session_state
    assert screen.CARDS_REJECTED_MESSAGE in labels(at, "warning")
    assert not any("예시 카드" in w for w in labels(at, "warning"))
    at = click(at, screen.RETRY_CARDS_LABEL)
    assert calls == [False, False] and at.session_state["step"] == 2
    assert "proposal" in at.session_state and "demo_reason" not in at.session_state
    assert screen.CARDS_REJECTED_MESSAGE not in labels(at, "warning")


def test_key_setting_error_is_shown_on_step_one(monkeypatch):
    import agent.proposals
    from agent.idea_cards import CardGenerationError
    from agent.llm import LLMError

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")

    def bad_key(request, *, demo=True, **kw):
        try:
            raise LLMError(
                "API 키가 올바르지 않아요. .env의 LLM_API_KEY를 확인해주세요. (HTTP 401)"
            )
        except LLMError as cause:
            raise CardGenerationError(f"아이디어 생성 중 AI 호출에 실패했어요. {cause}") from cause

    monkeypatch.setattr(agent.proposals, "propose_idea_cards", bad_key)
    at = click(confirm(), "아이디어 보기")
    assert at.session_state["step"] == 1 and "proposal" not in at.session_state
    assert any("API 키가 올바르지 않아요" in w for w in labels(at, "warning"))


def test_non_ai_card_error_stays_on_step_one(monkeypatch):
    import agent.proposals
    from agent.idea_cards import CardGenerationError

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")

    def few(request, *, demo=True, **kw):
        raise CardGenerationError(
            "조건에 맞는 형식이 3개보다 적어요. 관심 소재나 계절 조건을 넓혀 다시 시도해주세요."
        )

    monkeypatch.setattr(agent.proposals, "propose_idea_cards", few)
    at = click(confirm(), "아이디어 보기")
    assert at.session_state["step"] == 1 and "proposal" not in at.session_state
    assert any("조건에 맞는 형식이 3개보다 적어요" in w for w in labels(at, "warning"))


def test_real_demo_card_fails_january_and_moves_to_december(no_llm, monkeypatch):
    """실제 데모 카드(추천 1월)는 애월에서 시기 확인에 실패하고 12월로 고쳐진다 (시연 흐름)."""
    import agent.proposals
    from agent import demo_cards

    monkeypatch.setattr(agent.proposals, "demo_proposal", demo_cards.demo_proposal)
    at = to_results("제주시 애월읍")
    run = VerificationRun.model_validate(at.session_state["run"])
    assert run.rounds[0].results[0].check == "check_timing"
    assert run.rounds[0].results[0].status == "fail"
    assert run.final.timing.recommended_months == [12]
    assert run.outcome == "ready_for_approval"
    shown = [m.value for m in at.markdown]
    assert any(v.startswith("**추천 시기: 1월 → 12월") for v in shown)
    assert not at.exception


def test_demo_toggle_is_in_options_and_explains_how_to_turn_off(no_llm):
    at = confirm()
    options = next(e for e in at.expander if e.label == "시연 옵션")
    toggle = next(c for c in options.checkbox if c.label == screen.DEMO_TOGGLE_LABEL)
    assert screen.DEMO_TOGGLE_LABEL == "시연용 예시 카드 보기 (AI 없이)"
    assert toggle.value is False  # 기본은 꺼짐
    toggle.check().run()  # 시연 조건을 채운 뒤 사용자가 확인하고 제출
    click(at, "아이디어 보기")
    notice = next(e for e in at.expander if e.label == "예시 카드예요")
    chosen = [m.value for m in notice.markdown if screen.CHOSEN_DEMO_WARNING in m.value]
    assert chosen and "① 조건 입력에서 체크를 끄면" in chosen[0]
    assert not any(screen.DEMO_WARNING in m.value for m in notice.markdown)  # AI 오류 안내는 안 나옴


def test_demo_toggle_prefills_conditions_before_submission(no_llm, monkeypatch):
    from agent import demo_cards

    monkeypatch.setattr("agent.proposals.demo_proposal", demo_cards.demo_proposal)

    def no_ai(*args, **kwargs):
        raise AssertionError("시연에서는 AI를 호출하면 안 된다")

    monkeypatch.setattr("agent.proposals.default_llm", no_ai)
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.checkbox[0].check().run()
    assert not at.exception
    assert at.selectbox[0].value == "제주시 애월읍"
    assert at.selectbox[1].value == "겨울"
    assert at.text_input[2].value == "감귤"
    assert at.text_input[3].value == "가족"
    assert at.number_input[0].value == 10_000_000
    assert at.session_state["step"] == 1
    assert "request" not in at.session_state and "proposal" not in at.session_state
    click(at, "아이디어 보기")
    assert at.session_state["request"]["region"] == "제주시 애월읍"
    pick(at)
    run = VerificationRun.model_validate(at.session_state["run"])
    assert run.original.timing.recommended_months == [1]
    assert run.final.timing.recommended_months == [12]
    results = {r.check: r for r in run.rounds[-1].results}
    assert results["check_timing"].status != "pending"
    assert results["check_venue"].status == "pass"
    assert screen.venue_table(results["check_venue"])
    assert not at.exception


def test_demo_conditions_remain_editable_and_toggle_off_keeps_values(no_llm):
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.checkbox[0].check().run()
    at.selectbox[0].select("서귀포시 대정읍")
    at.number_input[0].set_value(5_000_000)
    click(at, "아이디어 보기")
    assert at.session_state["request"]["region"] == "서귀포시 대정읍"
    assert at.session_state["request"]["budget_max_krw"] == 5_000_000
    assert not at.exception

    at = AppTest.from_file(APP, default_timeout=120).run()
    at.checkbox[0].check().run()
    at.checkbox[0].uncheck().run()
    assert at.selectbox[0].value == "제주시 애월읍"
    assert at.number_input[0].value == 10_000_000
    assert "proposal" not in at.session_state


def test_demo_warning_text_by_reason():
    chosen = screen.demo_warning_text(screen.CHOSEN_DEMO_REASON, ["지역: 입력 A · 카드 B"])
    assert screen.CHOSEN_DEMO_WARNING in chosen and screen.DEMO_WARNING not in chosen
    assert "입력과 다른 점: 지역: 입력 A · 카드 B" in chosen
    quota = screen.demo_warning_text(screen.QUOTA_REASON, [])
    assert (
        screen.DEMO_WARNING in quota and f"이유: {screen.QUOTA_REASON}" in quota
    )  # AI 오류는 그대로
    assert screen.CHOSEN_DEMO_WARNING not in quota


def test_sentence_fills_first_screen_without_second_confirmation(no_llm, monkeypatch):
    from types import SimpleNamespace

    from agent.draft_contracts import UserRequest

    monkeypatch.setattr(
        "agent.request_parser.parse_request",
        lambda sentence: SimpleNamespace(
            request=UserRequest(region="제주시 애월읍", interest="감귤"), notes=[]
        ),
    )
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.text_input[0].input("애월 감귤 축제")
    click(at, "문장으로 조건 정리하기")
    assert not at.exception
    assert at.selectbox[0].value == "제주시 애월읍"
    assert at.text_input[2].value == "감귤"
    assert "request" not in at.session_state
    assert not any(b.label == "이 조건으로 확정" for b in at.button)
    assert len([b for b in at.button if b.label == "아이디어 보기"]) == 1
    assert not any("이 조건이 맞나요?" in str(el.value) for el in at.get("html"))
    at.text_input[2].input("방어")
    click(at, "아이디어 보기")
    assert at.session_state["step"] == 2
    assert at.session_state["request"]["interest"] == "방어"
    assert not at.exception


def test_idea_details_can_close_without_selecting(no_llm):
    at = click(confirm(), "아이디어 보기")
    assert len([b for b in at.button if b.label == "자세히 보기"]) == 3
    assert not any(b.label == "이 아이디어 고르기" for b in at.button)
    assert "selected" not in at.session_state
    [b for b in at.button if b.label == "자세히 보기"][1].click().run()
    assert not at.exception
    assert at.session_state["step"] == 2
    assert "selected" not in at.session_state
    assert not any(c.value.startswith("출처:") for c in at.caption)
    assert any("데이터 출처" in c.value for c in at.caption)
    click(at, "닫기")
    assert not at.exception
    assert at.session_state["step"] == 2
    assert not any(b.label == "이 아이디어 고르기" for b in at.button)
    assert "selected" not in at.session_state
    pick(at, 1)
    assert at.session_state["selected"] == demo_proposal().ideas[1].idea_id
    assert at.session_state["step"] == 3


def test_idea_summary_preserves_missing_data_and_budget(no_llm):
    card = CARD.model_copy(deep=True)
    rows = screen.idea_summary(card)
    assert str(card.evidence.trend.new_count) in rows[0][1]
    card.evidence.trend.status = "pending"
    card.evidence.jeju_gap.status = "pending"
    card.budget.format_median_krw = None
    rows = screen.idea_summary(card)
    assert all(row[2] == "데이터 대기" for row in rows)


def test_check_selection_and_plan_strip_html():
    from app import style

    head = style.check_selection_html(CARD)
    assert "고른 아이디어" in head and CARD.title in head and CARD.material in head
    strip = style.plan_strip_html("내가 고친 안", CARD, ready=False)
    assert "진행 불가" in strip and screen.NO_VENUE in strip
    assert screen.months_text(CARD.timing.recommended_months) in strip
    assert "진행 가능" in style.plan_strip_html("에이전트 추천안", CARD, ready=True)



def test_plan_markdown_editor_save_and_unsaved_guard(no_llm, monkeypatch, tmp_path):
    import agent.plan
    import agent.proposals
    from agent.draft_contracts import FestivalPlan

    monkeypatch.setattr(agent.proposals, "default_llm", lambda: FakePlanLLM())
    save = agent.plan.save_plan
    saves = []

    def save_explicitly(plan):
        saves.append(plan.version)
        return save(plan, tmp_path)

    monkeypatch.setattr(agent.plan, "save_plan", save_explicitly)
    at = to_results()
    next(b for b in at.button if b.label == "이대로 진행").click().run()
    assert not at.exception
    assert saves == []  # 생성 직후에는 저장 함수를 호출하지 않는다.
    assert any(el.proto.label == ".json 다운로드" for el in at.get("download_button"))
    assert not any("저장: outputs/" in value for value in labels(at, "caption"))
    editor = next(t for t in at.text_area if t.label == "기획서 Markdown")
    original = FestivalPlan.model_validate(at.session_state["plan"])
    edited = editor.value.replace(f"| 축제명 | {original.overview.name} |", "| 축제명 | 수정한 감귤 마켓 |")
    editor.set_value(edited).run()
    assert next(b for b in at.button if b.label == "기획서 최종 승인").disabled
    next(b for b in at.button if b.label == "수정 내용 적용").click().run()
    assert not at.exception
    revised = FestivalPlan.model_validate(at.session_state["plan"])
    assert revised.version == 2 and revised.overview.name == "수정한 감귤 마켓"
    assert saves == []  # 적용은 파일 저장을 하지 않는다.
    html = "".join(str(el.value) for el in at.get("html"))
    assert "fl-plan-document" in html and "fl-plan-kpi" in html
    assert "수정한 감귤 마켓" in html and "fl-plan-table overview" in html
    assert not next(b for b in at.button if b.label == "기획서 최종 승인").disabled

    assert saves == []
    next(b for b in at.button if b.label == "기획서 최종 승인").click().run()
    assert not at.exception and saves == []  # 승인은 디스크에 자동 저장하지 않는다.
