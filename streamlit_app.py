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
    order = [
        "request",
        "proposal",
        "selected",
        "run",
        "manual_run",
        "approved",
        "plan",
        "plan_path",
    ]
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
    budget = c6.number_input(
        "예산 상한 (원)",
        min_value=1,
        value=draft.get("budget_max_krw"),  # 한 문장에서 뽑힌 예산이 있으면 미리 채움, 없으면 빈칸
        step=1_000_000,
        placeholder="예: 10000000, 모르면 비워두세요",
    )
    confirmed = st.form_submit_button("이 조건으로 확정")
if confirmed:
    try:
        request = UserRequest(
            region=None if region == "(제주 전역)" else region,
            purpose=purpose.strip() or None,
            interest=interest.strip() or None,
            budget_max_krw=int(budget) if budget else None,  # 비어 있으면 미정
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
TOOLS_NOTE = "확인 도구 5개를 돌리는 중이에요…"


def tools():
    from agent.fake_checks import FAKE_TOOLS
    from analytics.real_checks import REAL_TOOLS

    return {**FAKE_TOOLS, **REAL_TOOLS}


if "run" not in ss:
    from agent.verify import verify_idea

    with st.spinner(TOOLS_NOTE):
        try:
            run = verify_idea(card, request, tools())
        except Exception as e:  # noqa: BLE001
            ui.error(str(e))
            stop()
    ss["run"] = run.model_dump(mode="json")
run = VerificationRun.model_validate(ss["run"])
manual = VerificationRun.model_validate(ss["manual_run"]) if "manual_run" in ss else None


def show_run(run: VerificationRun, with_changes: bool) -> None:
    """확인 결과 5개, 확인 과정 요약, (에이전트 추천안이면) 바뀐 점."""
    low_notes = screen.low_data_notes(run.rounds[-1].results)  # 지금(마지막 회차) 결과 기준
    if low_notes:
        ui.warning(f"⚠️ {screen.LOW_DATA_NOTICE}. " + ", ".join(low_notes) + ".")
    for line in screen.round_summary(run):
        ui.caption(line)
    for r in run.rounds[-1].results:
        with st.container(border=True):
            badge = " · 🧪 가상 데이터 포함" if r.is_synthetic else ""
            ui.markdown(
                f"**{screen.CHECK_LABELS[r.check]}** {screen.STATUS_ICONS[r.status]}{badge}"
            )
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
    if not with_changes:
        return
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
    with st.expander("확인 과정 자세히 보기"):
        for rd in run.rounds:
            ui.markdown(
                f"**{screen.ORDINALS.get(rd.round, rd.round)} 확인**: "
                + ", ".join(
                    f"{screen.CHECK_LABELS[x.check]} {screen.STATUS_ICONS[x.status]}"
                    for x in rd.results
                )
            )


def card_summary(c) -> str:
    venue = ", ".join(v.name for v in c.venue) or screen.NO_VENUE
    scale = screen.SCALE_LABELS.get(c.budget.scale, c.budget.scale)
    return (
        f"개최 월 {screen.months_text(c.timing.recommended_months)} · 장소 {venue} · 규모 {scale}"
    )


if manual is None:
    ui.caption("에이전트 추천안: " + card_summary(run.final))
    show_run(run, with_changes=True)
else:
    agent_tab, manual_tab = st.tabs(["에이전트 추천안", "내가 고친 안"])
    with agent_tab:
        ui.caption(card_summary(run.final))
        show_run(run, with_changes=True)
    with manual_tab:
        ui.caption(card_summary(manual.final))
        show_run(manual, with_changes=False)

# ---------- 직접 고쳐서 다시 확인 ----------
st.subheader("직접 고쳐서 다시 확인")
ui.caption("개최 월·장소·규모를 바꿔서 확인만 다시 해요. 자동으로 고치지는 않아요.")
base = (manual or run).final  # 처음 값은 지금 카드(가장 최근 안)의 값
places = screen.venue_choices(run)
place_names = [screen.NO_VENUE, *[p["name"] for p in places]]
current_place = base.venue[0].name if base.venue else screen.NO_VENUE
scale_names = list(screen.SCALE_LABELS.values())
with st.form("manual_form"):
    m1, m2, m3 = st.columns(3)
    months = m1.multiselect(
        "개최 월",
        list(range(1, 13)),
        default=base.timing.recommended_months,
        format_func=lambda m: f"{m}월",
    )
    place = m2.selectbox(
        "장소 (장소 후보 표에서)",
        place_names,
        index=place_names.index(current_place) if current_place in place_names else 0,
    )
    scale = m3.radio(
        "규모",
        scale_names,
        index=scale_names.index(screen.SCALE_LABELS.get(base.budget.scale, "기본")),
        horizontal=True,
    )
    recheck = st.form_submit_button("이 조건으로 다시 확인")
if recheck:
    if not months:
        ui.warning("개최 월을 하나 이상 골라주세요.")
    else:
        from agent.verify import verify_idea

        scale_value = next(k for k, v in screen.SCALE_LABELS.items() if v == scale)
        venue = next((p for p in places if p["name"] == place), None)
        try:
            edited = screen.edited_card(run.final, months, venue, scale_value)
            with st.spinner(TOOLS_NOTE):
                manual = verify_idea(
                    edited, request, tools(), max_fixes=0
                )  # 확인만, 자동 수정 없음
        except Exception as e:  # noqa: BLE001
            ui.error(str(e))
        else:
            reset_after("manual_run")
            ss["manual_run"] = manual.model_dump(mode="json")
            st.rerun()

# ---------- 4. 기획서 ----------
st.header("4. 기획서")
options = {"에이전트 추천안": run}
if manual is not None:
    options["내가 고친 안"] = manual
chosen_name = st.radio("어느 안으로 진행할까요?", list(options), horizontal=True)
chosen = options[chosen_name]
if ss.get("approved") and ss["approved"] != chosen_name:
    # 진행할 안을 바꾸면 예전 안으로 만든 기획서를 지운다 (다시 확인할 때는 reset_after("manual_run")이 지움)
    for key in ("approved", "plan", "plan_path"):
        ss.pop(key, None)
ready = chosen.outcome == "ready_for_approval"
if not ready:
    if chosen_name == "내가 고친 안":
        ui.warning(
            "❌ 항목이 남아 있어 기획서를 만들 수 없어요. 다른 값을 바꿔서 다시 확인해보세요."
        )
    else:
        ui.warning(
            "고쳐도 통과하지 못한 확인이 있어요. 직접 고쳐서 다시 확인하거나 다른 아이디어를 골라보세요."
        )
if st.button("이대로 진행", disabled=not ready):
    ss.pop("plan", None)
    ss["approved"] = chosen_name
if ss.get("approved") and ss["approved"] in options:
    approved_run = options[ss["approved"]]
    try:
        from agent.plan import PlanGenerationError, generate_plan, plan_to_markdown, save_plan
    except ImportError:
        ui.info("기획서 기능 준비 중이에요.")
    else:
        from agent.draft_contracts import FestivalPlan

        if "plan" not in ss:
            # 장소 후보를 기획서에 넘기는 방식은 A와 정할 예정. 지금은 고른 안의 확인 결과 그대로 넘긴다
            try:
                with st.spinner("기획서를 쓰는 중이에요…"):
                    plan = generate_plan(approved_run, request, approved=True)
            except PlanGenerationError as e:
                ui.warning(str(e))
            except Exception as e:  # noqa: BLE001
                ui.error(str(e))
            else:
                md_path, _ = save_plan(plan)
                ss["plan"] = plan.model_dump(mode="json")
                ss["plan_path"] = str(md_path)
        if "plan" in ss:
            plan = FestivalPlan.model_validate(ss["plan"])
            ui.success(f"{ss['approved']}으로 기획서를 만들었어요.")
            ui.markdown(plan_to_markdown(plan))
            ui.caption(f"저장: {ss.get('plan_path', '')}")
            if plan.is_synthetic:
                ui.warning("가짜·합성 데이터 결과가 섞여 있어요.")

footer()
