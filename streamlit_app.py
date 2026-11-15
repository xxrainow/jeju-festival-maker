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


class _EscapedText:
    """st.markdown/write/caption/info/warning/error/success에 넘기는 문장의 "~"를 이스케이프한다 (취소선 방지)."""

    def __getattr__(self, name):
        fn = getattr(st, name)

        def call(*args, **kwargs):
            return fn(*(screen.md(a) for a in args), **kwargs)

        return call


ui = _EscapedText()

st.set_page_config(page_title="제주 축제랩", page_icon="🍊", layout="wide")
settings = Settings()
has_llm = bool(settings.llm_api_key.get_secret_value())
AREAS = sorted(EMD_CODES.values())
ss = st.session_state


def footer() -> None:
    st.divider()
    ui.caption("데이터 출처")
    for s in screen.DATA_SOURCES:
        ui.caption(f"- {s}")


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
ui.write(
    "전국 축제 트렌드와 제주 데이터로 우리 동네 축제 아이디어를 만들고, 제주 데이터로 확인해요."
)

with st.sidebar:
    st.header("설정")
    ui.write("AI(LLM) 설정:", "있음" if has_llm else "없음")
    if not has_llm:
        ui.caption(
            "AI 설정이 없으면 한 문장 입력·새 카드·기획서는 안내 문구로 대신해요. 데모 카드로 흐름을 볼 수 있어요."
        )
    ui.caption("API Key는 화면에 표시하지 않아요.")

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
        ui.warning(str(e))
        ui.caption("아래 칸에 직접 입력해 주세요.")
    except Exception as e:  # noqa: BLE001 - 예상 못 한 오류도 문장 그대로 보여준다
        ui.error(str(e))
    else:
        ss["draft"] = parsed.request.model_dump(mode="json")
        ss["notes"] = parsed.notes
for note in ss.get("notes", []):
    ui.info(note)

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
        ui.error(str(e))
    else:
        reset_after("request")
        ss["request"] = request.model_dump(mode="json")

if "request" not in ss:
    stop()
request = UserRequest.model_validate(ss["request"])
ui.success(
    f"확정한 조건: 지역 {request.region or '제주 전역'}, 목적 {request.purpose or '미정'}, "
    f"소재 {request.interest or '미정'}, 계절 {request.season or '미정'}, 대상 {request.target or '미정'}, "
    f"예산 {screen.won(request.budget_max_krw)}"
)
if conflict := screen.season_conflict(request):
    ui.warning(f"⚠️ {conflict}")  # 막지 않고 안내만

# ---------- 2. 아이디어 카드 ----------
st.header("2. 아이디어 카드")
use_demo = st.checkbox("데모 카드로 보기 (입력과 상관없이 같은 예시 카드)", value=not has_llm)
if st.button("아이디어 카드 받기"):
    from agent.idea_cards import CardGenerationError
    from agent.proposals import propose_idea_cards

    try:
        proposal = propose_idea_cards(request, demo=use_demo)
    except CardGenerationError as e:
        ui.warning(str(e))
    except Exception as e:  # noqa: BLE001
        ui.error(str(e))
    else:
        reset_after("proposal")
        ss["proposal"] = proposal.model_dump(mode="json")

if "proposal" not in ss:
    stop()
proposal = IdeaProposal.model_validate(ss["proposal"])
if proposal.is_demo:
    diffs = screen.demo_differences(proposal, request)
    ui.warning(
        f"### ⚠️ 예시 카드예요\n**{screen.DEMO_WARNING}**"
        + ("\n\n입력과 다른 점: " + " / ".join(diffs) if diffs else "")
    )
for notice in proposal.notices:
    ui.info(notice)

cols = st.columns(3)
for col, card in zip(cols, proposal.ideas, strict=True):  # rank 순서, rank·score는 보여주지 않음
    with col, st.container(border=True):
        st.subheader(card.title)
        ui.write(card.concept)
        ui.caption(f"{card.format} × {card.material}")
        for title, body, source in screen.evidence_lines(card):
            ui.markdown(f"**{title}**")
            if body:
                ui.write(body)
            ui.caption(f"출처: {source}")
        ui.markdown(f"**{screen.reference_text(card)}**")
        ui.markdown(f"**{screen.timing_text(card)}**")
        ui.markdown("**예산**")
        for line in screen.budget_lines(card):
            ui.caption(line)
        ui.markdown("**고르면 확인할 것**")
        for h in card.hypotheses:
            ui.write(f"- {screen.check_phrase(h)}")
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
            ui.error(str(e))
            stop()
    ss["run"] = run.model_dump(mode="json")
run = VerificationRun.model_validate(ss["run"])

from agent.verify import summarize

last = run.rounds[-1]
low_notes = screen.low_data_notes(run.rounds[-1].results)  # 지금(마지막 회차) 결과 기준
if low_notes:
    ui.warning(f"⚠️ {screen.LOW_DATA_NOTICE}. " + ", ".join(low_notes) + ".")
ui.caption(f"확인 {len(run.rounds)}회 (처음 1회 + 고친 뒤 {len(run.rounds) - 1}회). 마지막 결과:")
for r in last.results:
    with st.container(border=True):
        badge = " · 🧪 가상 데이터 포함" if r.is_synthetic else ""
        ui.markdown(f"**{screen.CHECK_LABELS[r.check]}** {screen.STATUS_ICONS[r.status]}{badge}")
        ui.write(r.reason)
        for line in screen.key_numbers(r):
            ui.caption(line)
        if r.check == "check_venue" and (rows := screen.venue_table(r)):
            st.dataframe(pd.DataFrame(rows), hide_index=True)
        if r.sources:
            ui.caption("출처: " + " / ".join(r.sources))
        if r.warnings:
            with st.expander("주의할 점"):
                for w in r.warnings:
                    ui.write(f"- {w}")

st.subheader("바뀐 점")
changes = screen.friendly_changes(run)
if not changes:
    ui.write("바뀐 점이 없어요.")
for ch in changes:
    with st.container(border=True):
        ui.markdown(f"**{ch['title']}**")
        ui.write(ch["reason"])
        if ch["note"]:
            ui.write(f"⚠️ {ch['note']}")
        if ch["low_data"]:
            ui.write(f"⚠️ {screen.LOW_DATA_NOTICE}. " + ", ".join(ch["low_data"]) + ".")
        for n in ch["numbers"]:
            ui.caption(n)
        if ch["season"]:
            ui.caption(ch["season"])
with st.expander("확인 기록 (회차별)"):
    for rd in run.rounds:
        ui.markdown(
            f"**{rd.round}회차**: "
            + ", ".join(
                f"{screen.CHECK_LABELS[x.check]} {screen.STATUS_ICONS[x.status]}"
                for x in rd.results
            )
        )
    ui.caption("개발자용 원문 (summarize)")
    for line in summarize(run):
        st.code(line, language=None)

if run.outcome != "ready_for_approval":
    ui.warning("고쳐도 통과하지 못한 확인이 있어요. 다른 아이디어를 골라보세요.")
    stop()

# ---------- 4. 기획서 ----------
st.header("4. 기획서")
if st.button("이대로 진행"):
    ss["approved"] = True
if ss.get("approved"):
    try:
        from agent.plan import PlanGenerationError, generate_plan, plan_to_markdown, save_plan
    except ImportError:
        ui.info(
            "기획서 기능 준비 중이에요. A의 기획서 생성(agent/plan.py)이 main에 합쳐지면 바로 연결돼요."
        )
    else:
        # 장소 후보를 기획서에 넘기는 방식은 A와 정할 예정. 지금은 확인 결과(run) 그대로 넘긴다
        try:
            plan = generate_plan(run, request, approved=True)
        except PlanGenerationError as e:
            ui.warning(str(e))
        except Exception as e:  # noqa: BLE001
            ui.error(str(e))
        else:
            ui.markdown(plan_to_markdown(plan))
            md_path, _ = save_plan(plan)
            ui.caption(f"저장: {md_path}")
            if plan.is_synthetic:
                ui.warning("가짜·합성 데이터 결과가 섞여 있어요.")

footer()
