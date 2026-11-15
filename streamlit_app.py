"""제주 축제랩 화면 (docs/a-guide.md 순서).

한 문장 입력 → 조건 확정 → 아이디어 카드 3장 → 선택 → 확인 도구 5개 검증·수정 → 이대로 진행 → 기획서.
st.session_state에는 모델을 model_dump(mode="json")로 저장하고 model_validate로 읽는다.
"""

import pandas as pd
import streamlit as st

from agent.draft_contracts import IdeaProposal, UserRequest, VerificationRun
from analytics.flow_spec import EMD_CODES
from app import screen
from app.settings import Settings

st.set_page_config(page_title="제주 축제랩", page_icon="🍊", layout="wide")
settings = Settings()
has_llm = bool(settings.llm_api_key.get_secret_value())
AREAS = sorted(EMD_CODES.values())
ss = st.session_state


def footer() -> None:
    st.divider()
    st.caption("데이터 출처")
    for s in screen.DATA_SOURCES:
        st.caption(f"- {s}")


def stop() -> None:
    """출처 문구를 남기고 여기서 멈춘다."""
    footer()
    st.stop()


def reset_after(step: str) -> None:
    """앞 단계가 바뀌면 뒤 단계 결과를 지운다."""
    order = ["request", "proposal", "selected", "run", "approved"]
    for key in order[order.index(step) :]:
        ss.pop(key, None)


st.title("🍊 제주 축제랩")
st.write(
    "전국 축제 트렌드와 제주 데이터로 우리 동네 축제 아이디어를 만들고, 제주 데이터로 확인해요."
)

with st.sidebar:
    st.header("설정")
    st.write("AI(LLM) 설정:", "있음" if has_llm else "없음")
    if not has_llm:
        st.caption(
            "AI 설정이 없으면 한 문장 입력·새 카드·기획서는 안내 문구로 대신해요. 데모 카드로 흐름을 볼 수 있어요."
        )
    st.caption("API Key는 화면에 표시하지 않아요.")

# ---------- 1. 조건 입력 ----------
st.header("1. 어떤 축제를 열고 싶나요?")
sentence = st.text_input(
    "한 문장으로 적어주세요",
    placeholder="예: 대정읍 방어 축제, 상권 활성화, 11~12월, 가족, 예산 1천만 원",
)
if st.button("조건 채우기"):
    from agent.request_parser import RequestParseError, parse_request

    try:
        parsed = parse_request(sentence)
    except RequestParseError as e:
        st.warning(str(e))
        st.caption("아래 칸에 직접 입력해 주세요.")
    except Exception as e:  # noqa: BLE001 - 예상 못 한 오류도 문장 그대로 보여준다
        st.error(str(e))
    else:
        ss["draft"] = parsed.request.model_dump(mode="json")
        ss["notes"] = parsed.notes
for note in ss.get("notes", []):
    st.info(note)

draft = ss.get("draft", {})
with st.form("request_form"):
    c1, c2, c3 = st.columns(3)
    region_options = ["(제주 전역)", *AREAS]
    region = c1.selectbox(
        "지역 (행정동·읍면)",
        region_options,
        index=region_options.index(draft["region"]) if draft.get("region") in AREAS else 0,
    )
    purpose = c2.text_input("목적", value=draft.get("purpose") or "")
    c2.caption("예: " + ", ".join(screen.PURPOSES))
    interest = c3.text_input("관심 소재", value=draft.get("interest") or "")
    c4, c5, c6 = st.columns(3)
    season_options = ["(미정)", *screen.SEASONS]
    season = c4.selectbox(
        "계절",
        season_options,
        index=season_options.index(draft["season"]) if draft.get("season") in screen.SEASONS else 0,
    )
    target = c5.text_input(
        "대상", value=draft.get("target") or "", placeholder="가족, 청년, 어르신 …"
    )
    budget_known = c6.checkbox("예산 상한이 있어요", value=draft.get("budget_max_krw") is not None)
    budget = c6.number_input(
        "예산 상한 (원)",
        min_value=1,
        value=int(draft.get("budget_max_krw") or 10_000_000),
        step=1_000_000,
    )
    confirmed = st.form_submit_button("이 조건으로 확정")
if confirmed:
    try:
        request = UserRequest(
            region=None if region == "(제주 전역)" else region,
            purpose=purpose.strip() or None,
            interest=interest.strip() or None,
            budget_max_krw=int(budget) if budget_known else None,
            season=None if season == "(미정)" else season,
            target=target.strip() or None,
        )
    except Exception as e:  # noqa: BLE001 - 계약 검사 오류를 그대로 보여준다
        st.error(str(e))
    else:
        reset_after("request")
        ss["request"] = request.model_dump(mode="json")

if "request" not in ss:
    stop()
request = UserRequest.model_validate(ss["request"])
st.success(
    f"확정한 조건: 지역 {request.region or '제주 전역'}, 목적 {request.purpose or '미정'}, "
    f"소재 {request.interest or '미정'}, 계절 {request.season or '미정'}, 대상 {request.target or '미정'}, "
    f"예산 {screen.won(request.budget_max_krw)}"
)

# ---------- 2. 아이디어 카드 ----------
st.header("2. 아이디어 카드")
use_demo = st.checkbox("데모 카드로 보기 (입력과 상관없이 같은 예시 카드)", value=not has_llm)
if st.button("아이디어 카드 받기"):
    from agent.idea_cards import CardGenerationError
    from agent.proposals import propose_idea_cards

    try:
        proposal = propose_idea_cards(request, demo=use_demo)
    except CardGenerationError as e:
        st.warning(str(e))
    except Exception as e:  # noqa: BLE001
        st.error(str(e))
    else:
        reset_after("proposal")
        ss["proposal"] = proposal.model_dump(mode="json")

if "proposal" not in ss:
    stop()
proposal = IdeaProposal.model_validate(ss["proposal"])
for notice in proposal.notices:
    st.info(notice)

cols = st.columns(3)
for col, card in zip(cols, proposal.ideas, strict=True):  # rank 순서, rank·score는 보여주지 않음
    with col, st.container(border=True):
        st.subheader(card.title)
        st.write(card.concept)
        st.caption(f"{card.format} × {card.material}")
        for question, value, source in screen.evidence_lines(card):
            st.markdown(f"**{question}** {value}")
            st.caption(f"출처: {source}")
        ref = card.reference
        names = ", ".join(f.name for f in ref.designated_festivals)
        st.markdown(f"**사례** {ref.type}" + (f": {names}" if names else ""))
        fest = card.timing.jeju_festivals_in_month
        st.markdown(
            f"**추천 시기** {screen.months_text(card.timing.recommended_months)}"
            + (f" (그 달 제주 축제 {fest}개)" if fest is not None else "")
        )
        st.markdown("**예산**")
        for line in screen.budget_lines(card):
            st.caption(line)
        st.markdown("**검증할 가설**")
        for h in card.hypotheses:
            st.write(f"- {h}")
        if st.button("이 아이디어 고르기", key=f"pick_{card.idea_id}"):
            reset_after("selected")
            ss["selected"] = card.idea_id

if "selected" not in ss:
    stop()
card = next(c for c in proposal.ideas if c.idea_id == ss["selected"])

# ---------- 3. 제주 데이터로 확인 ----------
st.header(f"3. 제주 데이터로 확인: {card.title}")
if "run" not in ss:
    from agent.fake_checks import FAKE_TOOLS
    from agent.verify import verify_idea
    from analytics.real_checks import REAL_TOOLS

    with st.spinner("확인 도구 5개를 돌리는 중이에요…"):
        try:
            run = verify_idea(card, request, {**FAKE_TOOLS, **REAL_TOOLS})
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
            stop()
    ss["run"] = run.model_dump(mode="json")
run = VerificationRun.model_validate(ss["run"])

from agent.verify import summarize

last = run.rounds[-1]
st.caption(f"확인 {len(run.rounds)}회 (처음 1회 + 고친 뒤 {len(run.rounds) - 1}회). 마지막 결과:")
for r in last.results:
    with st.container(border=True):
        badge = " · 🧪 가상 데이터 포함" if r.is_synthetic else ""
        st.markdown(f"**{screen.CHECK_LABELS[r.check]}** {screen.STATUS_ICONS[r.status]}{badge}")
        st.write(r.reason)
        for line in screen.key_numbers(r):
            st.caption(line)
        if r.check == "check_venue" and (rows := screen.venue_table(r)):
            st.dataframe(pd.DataFrame(rows), hide_index=True)
        if r.sources:
            st.caption("출처: " + " / ".join(r.sources))
        if r.warnings:
            with st.expander("주의할 점"):
                for w in r.warnings:
                    st.write(f"- {w}")

st.subheader("바뀐 점")
lines = summarize(run)
if lines:
    for line in lines:
        st.write(f"- {line}")
else:
    st.write("바뀐 점이 없어요.")
with st.expander("확인 기록 (회차별)"):
    for rd in run.rounds:
        st.markdown(
            f"**{rd.round}회차**: "
            + ", ".join(
                f"{screen.CHECK_LABELS[x.check]} {screen.STATUS_ICONS[x.status]}"
                for x in rd.results
            )
        )

if run.outcome != "ready_for_approval":
    st.warning("고쳐도 통과하지 못한 확인이 있어요. 다른 아이디어를 골라보세요.")
    stop()

# ---------- 4. 기획서 ----------
st.header("4. 기획서")
if st.button("이대로 진행"):
    ss["approved"] = True
if ss.get("approved"):
    try:
        from agent.plan import PlanGenerationError, generate_plan, plan_to_markdown, save_plan
    except ImportError:
        st.info(
            "기획서 기능 준비 중이에요. A의 기획서 생성(agent/plan.py)이 main에 합쳐지면 바로 연결돼요."
        )
    else:
        # 장소 후보를 기획서에 넘기는 방식은 A와 정할 예정. 지금은 확인 결과(run) 그대로 넘긴다
        try:
            plan = generate_plan(run, request, approved=True)
        except PlanGenerationError as e:
            st.warning(str(e))
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
        else:
            st.markdown(plan_to_markdown(plan))
            md_path, _ = save_plan(plan)
            st.caption(f"저장: {md_path}")
            if plan.is_synthetic:
                st.warning("가짜·합성 데이터 결과가 섞여 있어요.")

footer()
