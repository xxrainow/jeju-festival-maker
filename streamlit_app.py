"""제주 축제랩 화면 (docs/a-guide.md 순서). 한 번에 한 단계만 보여준다.

① 조건 입력 → ② 아이디어 → ③ 데이터로 확인 → ④ 기획서 → ⑤ 홍보물
지금 단계는 session_state["step"]. 앞 단계로 돌아가서 값을 바꾸면 뒤 단계 결과는 지운다 (reset_after).
st.session_state에는 모델을 model_dump(mode="json")로 저장하고 model_validate로 읽는다.
"""

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from agent.draft_contracts import IdeaProposal, UserRequest, VerificationRun
from analytics.flow_spec import EMD_CODES
from app import screen, style
from app.settings import Settings


class _EscapedText:
    """st.markdown/write/caption/info/warning/error/success에 넘기는 문장의 "~"를 이스케이프한다 (취소선 방지)."""

    def __getattr__(self, name):
        fn = getattr(st, name)

        def call(*args, **kwargs):
            return fn(*(screen.md(a) for a in args), **kwargs)

        return call


ui = _EscapedText()

st.set_page_config(
    page_title="제주 축제랩", page_icon="🍊", layout="wide", initial_sidebar_state="collapsed"
)
settings = Settings()
has_llm = bool(settings.llm_api_key.get_secret_value())
AREAS = sorted(EMD_CODES.values())
TOOLS_NOTE = "확인 도구 5개를 돌리는 중이에요…"
ss = st.session_state


# ---------- 공통 ----------


def footer() -> None:
    st.html(style.evidence_legend_html())
    with st.container(key="foot"):
        ui.caption("데이터 출처")
        ui.caption(" · ".join(screen.DATA_SOURCES))


def reset_after(step: str) -> None:
    """앞 단계가 바뀌면 뒤 단계 결과를 지운다."""
    order = [
        "request",
        "idea_retry",
        "proposal",
        "demo_reason",
        "detail_idea",
        "selected",
        "run",
        "manual_run",
        "approved",
        "promo",
        "plan",
        "plan_error",
        "plan_path",
    ]
    for key in order[order.index(step) :]:
        ss.pop(key, None)


def goto(step: int) -> None:
    """단계를 바꾸고 화면 맨 위부터 다시 그린다."""
    ss["step"] = step
    ss["scroll_top"] = True
    st.rerun()


def back_button(step: int) -> None:
    if st.button("← 이전 단계로", key=f"back_{step}"):
        goto(step - 1)


def tools():
    from agent.fake_checks import FAKE_TOOLS
    from analytics.real_checks import REAL_TOOLS

    return {**FAKE_TOOLS, **REAL_TOOLS}


def current_request() -> UserRequest | None:
    return UserRequest.model_validate(ss["request"]) if "request" in ss else None


def current_card():
    if "proposal" not in ss or "selected" not in ss:
        return None
    proposal = IdeaProposal.model_validate(ss["proposal"])
    return next((c for c in proposal.ideas if c.idea_id == ss["selected"]), None)


def run_options() -> dict[str, VerificationRun]:
    """진행할 수 있는 안: 에이전트 추천안, (있으면) 내가 고친 안."""
    options = {}
    if "run" in ss:
        options["에이전트 추천안"] = VerificationRun.model_validate(ss["run"])
    if "manual_run" in ss:
        options["내가 고친 안"] = VerificationRun.model_validate(ss["manual_run"])
    return options


def current_plan():
    from agent.draft_contracts import FestivalPlan

    return FestivalPlan.model_validate(ss["plan"]) if "plan" in ss else None


def reachable_step() -> int:
    """지금 상태로 갈 수 있는 가장 뒤 단계."""
    if "request" not in ss or "proposal" not in ss:
        return 1
    if current_card() is None:
        return 2
    if not ss.get("approved") or ss["approved"] not in run_options():
        return 3
    plan = current_plan()
    if plan is None or plan.status != "approved":
        return 4
    return 5


# ---------- ① 조건 입력 ----------


def parse_sentence() -> None:
    """문장에서 뽑은 조건을 첫 화면의 입력 칸에 채운다."""
    from agent.request_parser import RequestParseError, parse_request

    sentence = ss.get("sentence", "")
    try:
        parsed = parse_request(sentence)
    except RequestParseError as e:
        ss["parse_error"] = ("warning", str(e))
    except Exception as e:  # noqa: BLE001 - 예상 못 한 오류도 문장 그대로 보여준다
        ss["parse_error"] = ("error", str(e))
    else:
        ss["draft"] = parsed.request.model_dump(mode="json")
        ss["notes"] = parsed.notes
        ss["draft_from_ai"] = True
        ss["parsed_sentence"] = sentence.strip()


def step_request() -> None:
    error = ss.pop("parse_error", None)
    st.html(style.HERO)
    with st.container(key="pill"):
        left, right = st.columns([5, 1.4], vertical_alignment="center")
        left.text_input(
            "한 문장으로 적어주세요",
            key="sentence",
            placeholder="예: 애월읍 감귤 축제, 상권 살리고, 겨울, 가족, 예산 1천만 원",
            label_visibility="collapsed",
        )
        right.button("문장으로 조건 정리하기", on_click=parse_sentence, use_container_width=True)
    ui.caption(
        "적은 문장에서 지역·계절·예산 등을 뽑아 아래 칸에 채워요. 채운 뒤 직접 고칠 수 있어요."
    )
    if error:
        kind, message = error
        if kind == "warning":
            ui.warning(message)
            ui.caption("아래 칸에 직접 입력해 주세요.")
        else:
            ui.error(message)
    for note in ss.get("notes", []):
        ui.info(note)
    if idea_error := ss.pop("idea_error", None):  # 아이디어 만들기에서 돌아온 조건 문제
        kind, message = idea_error
        (ui.warning if kind == "warning" else ui.error)(message)
    if ss.get("idea_retry") and current_request() is not None:
        # AI 카드가 규칙 검사에 걸림: 예시 카드로 넘어가지 않고 다시 받게 한다
        ui.warning(screen.CARDS_REJECTED_MESSAGE)
        if st.button(screen.RETRY_CARDS_LABEL, type="primary", key="retry_ideas"):
            ss["idea_job"] = {"demo": False}
            goto(2)

    draft = ss.get("draft") or ss.get("request") or {}
    from_ai = bool(ss.get("draft_from_ai"))

    def field(col, key: str, label: str):
        """Figma 조건 칸 카드: 이름 + (AI가 채움 / 비어 있음) 표시."""
        box = col.container(key=f"fieldcard-{key}")
        box.html(style.field_head_html(label, style.field_origin(draft.get(key), from_ai)))
        return box

    with st.form("request_form", border=False):
        c1, c2, c3 = st.columns(3)
        region_options = ["(제주 전역)", *AREAS]
        region = field(c1, "region", "지역 (읍면동)").selectbox(
            "지역 (행정동·읍면)",
            region_options,
            index=region_options.index(draft["region"]) if draft.get("region") in AREAS else 0,
            label_visibility="collapsed",
        )
        box = field(c2, "purpose", "목적")
        purpose = box.text_input(
            "목적", value=draft.get("purpose") or "", label_visibility="collapsed"
        )
        box.caption("예: " + ", ".join(screen.PURPOSES))
        interest = field(c3, "interest", "관심 소재").text_input(
            "관심 소재", value=draft.get("interest") or "", label_visibility="collapsed"
        )
        c4, c5, c6 = st.columns(3)
        season_options = ["(미정)", *screen.SEASONS]
        season = field(c4, "season", "계절").selectbox(
            "계절",
            season_options,
            index=season_options.index(draft["season"])
            if draft.get("season") in screen.SEASONS
            else 0,
            label_visibility="collapsed",
        )
        target = field(c5, "target", "대상").text_input(
            "대상",
            value=draft.get("target") or "",
            placeholder="가족, 청년, 어르신 …",
            label_visibility="collapsed",
        )
        budget = field(c6, "budget_max_krw", "예산 상한 (원)").number_input(
            "예산 상한 (원)",
            min_value=1,
            value=draft.get(
                "budget_max_krw"
            ),  # 한 문장에서 뽑힌 예산이 있으면 미리 채움, 없으면 빈칸
            step=1_000_000,
            placeholder="예: 10000000, 모르면 비워두세요",
            label_visibility="collapsed",
        )
        ui.info(
            "대상을 비우면 ‘대상’ 확인은 데이터 대기로 남아요. "
            "계절과 소재가 맞지 않으면 막지 않고 알려만 드려요."
        )
        with st.expander("시연 옵션"):
            use_demo = st.checkbox(screen.DEMO_TOGGLE_LABEL, value=False)
        confirmed = st.form_submit_button("아이디어 보기", type="primary")
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
            if ss.get("request") != request.model_dump(mode="json"):
                reset_after("request")  # 조건이 바뀌면 뒤 단계 결과를 지운다
            ss["request"] = request.model_dump(mode="json")
            ss["draft"] = ss["request"]
            if "proposal" in ss and not use_demo and not ss.get("demo_reason"):
                goto(2)  # 같은 조건이면 받아 둔 카드를 다시 보여준다
            ss["idea_job"] = {"demo": use_demo}
            goto(2)


def make_ideas(request: UserRequest) -> None:
    """02-1 아이디어 만드는 중: 단계별 진행 상황을 보여주며 카드를 만든 뒤 ② 아이디어로 간다."""
    from agent.idea_cards import CardGenerationError
    from agent.proposals import propose_idea_cards

    job = ss.pop("idea_job")
    ss.pop("idea_retry", None)
    st.html(
        style.head_html(
            2,
            "아이디어 카드를 만들고 있어요",
            "숫자는 코드가 계산하고, AI는 카드 문장만 써요. 보통 20초쯤 걸려요.",
        )
    )
    st.html(style.request_chips(request))
    panel = st.empty()
    for _ in range(40):  # 만드는 동안 이전 화면(① 조건 입력)이 흐리게 남지 않게 빈칸으로 덮는다
        st.empty()
    details: dict[int, str] = {}

    def progress(step: int, detail: str) -> None:
        details[step] = detail
        panel.html(style.progress_html(step, details))

    progress(1, style.IDEA_STEPS[0][1])
    reason = None
    if job["demo"]:
        reason = screen.CHOSEN_DEMO_REASON
    elif not has_llm:
        reason = screen.NO_KEY_REASON
    try:
        proposal = propose_idea_cards(request, demo=reason is not None, progress=progress)
    except CardGenerationError as e:
        if screen.cards_rejected(e):  # AI가 규칙에 맞는 카드를 못 만듦: ①에서 "다시 받기"
            ss["idea_retry"] = True
            goto(1)
        reason = screen.ai_failure_reason(e)
        if reason is None:  # 조건 문제·키 설정 오류 등: 원래 안내를 보여주고 ① 조건 입력에 머문다
            ss["idea_error"] = ("warning", str(e))
            goto(1)
        # 키 없음·429·연결 오류면 예시 카드로 대신
        proposal = propose_idea_cards(request, demo=True)
    except Exception as e:  # noqa: BLE001
        ss["idea_error"] = ("error", str(e))
        goto(1)
    panel.html(style.progress_html(len(style.IDEA_STEPS) + 1, details))
    reset_after("proposal")
    ss["proposal"] = proposal.model_dump(mode="json")
    if reason:
        ss["demo_reason"] = reason
    goto(2)


# ---------- ② 아이디어 ----------


def step_ideas(request: UserRequest) -> None:
    st.html(style.head_html(2))
    st.html(style.request_chips(request))
    if conflict := screen.season_conflict(request):
        ui.warning(f"⚠️ {conflict}")
    proposal = IdeaProposal.model_validate(ss["proposal"])
    if proposal.is_demo:
        diffs = screen.demo_differences(proposal, request)
        ui.warning(screen.demo_warning_text(ss.get("demo_reason"), diffs))
    for notice in proposal.notices:
        ui.info(notice)

    cols = st.columns(3)
    for col, card in zip(cols, proposal.ideas, strict=True):  # rank 순서, rank·score는 숨김
        with col, st.container(key=f"card-idea-{card.idea_id}"):
            st.html(style.format_html(f"{card.format} × {card.material}"))
            st.subheader(card.title)
            ui.write(card.concept)
            st.html(style.idea_summary_html(screen.idea_summary(card)))
            with st.container(key=f"soft-hyp-{card.idea_id}"):
                ui.caption("고르면 확인할 것")
                for h in card.hypotheses[:2]:
                    ui.write(f"- {screen.check_phrase(h)}")
            if st.button("자세히 보기", key=f"detail_{card.idea_id}", use_container_width=True):
                ss["detail_idea"] = card.idea_id
    detail = next((c for c in proposal.ideas if c.idea_id == ss.get("detail_idea")), None)
    if detail is not None:
        idea_details(detail)


def dismiss_idea_details() -> None:
    ss.pop("detail_idea", None)


@st.dialog("아이디어 자세히 보기", width="large", on_dismiss=dismiss_idea_details)
def idea_details(card) -> None:
    """근거는 상세 패널에서 읽고, 확인한 아이디어만 고른다."""
    st.html(style.idea_detail_html(card))
    with st.container(key="idea-detail-actions"):
        choose, close = st.columns([4, 1])
        if choose.button("이 아이디어 고르기", key=f"pick_{card.idea_id}",
                         type="primary", use_container_width=True):
            if ss.get("selected") != card.idea_id:
                reset_after("selected")
            ss["selected"] = card.idea_id
            dismiss_idea_details()
            goto(3)
        if close.button("닫기", use_container_width=True):
            dismiss_idea_details()
            st.rerun()


# ---------- ③ 데이터로 확인 ----------


def show_run(run: VerificationRun, with_changes: bool, key: str = "agent") -> None:
    """확인 결과 5개, 확인 과정 요약, (에이전트 추천안이면) 바뀐 점."""
    low_notes = screen.low_data_notes(run.rounds[-1].results)  # 지금(마지막 회차) 결과 기준
    if low_notes:
        ui.warning(f"⚠️ {screen.LOW_DATA_NOTICE}. " + ", ".join(low_notes) + ".")
    results = run.rounds[-1].results
    st.html(style.summary_html(results, f"확인 {len(run.rounds)}회"))
    for line in screen.round_summary(run):
        ui.caption(line)
    cols = st.columns(3)
    for i, r in enumerate(results):
        with cols[i % 3], st.container(key=f"res-{r.status}-{key}-{i}"):
            st.html(style.check_head_html(screen.CHECK_LABELS[r.check], r.status, r.is_synthetic))
            ui.write(r.reason)
            if r.check == "check_timing" and with_changes and (notice := screen.season_notice(run)):
                ui.write(f"⚠️ {notice}")  # 에이전트가 입력 계절 밖 달로 바꿨을 때
            with st.container(key=f"check-numbers-{key}-{i}"):
                for line in screen.key_numbers(r):
                    ui.caption(line)
            if r.check == "check_venue" and (rows := screen.venue_table(r)):
                st.dataframe(pd.DataFrame(rows), hide_index=True)
            if r.sources:
                with st.container(key=f"check-source-{key}-{i}"):
                    ui.caption("출처: " + " · ".join(r.sources))
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
    for j, ch in enumerate(changes):
        with st.container(key=f"chg-{key}-{j}"):
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


def step_check(request: UserRequest, card) -> None:
    with st.container(key="verification"):
        verification_content(request, card)


def verification_content(request: UserRequest, card) -> None:
    st.html(style.head_html(3))
    st.html(style.check_selection_html(card.title))
    if "run" not in ss:
        from agent.verify import verify_idea

        with st.spinner(TOOLS_NOTE):
            try:
                run = verify_idea(card, request, tools())
            except Exception as e:  # noqa: BLE001
                ui.error(str(e))
                return
        ss["run"] = run.model_dump(mode="json")
    run = VerificationRun.model_validate(ss["run"])
    manual = VerificationRun.model_validate(ss["manual_run"]) if "manual_run" in ss else None

    if manual is None:
        ui.caption("에이전트 추천안: " + card_summary(run.final))
        show_run(run, with_changes=True)
    else:
        agent_tab, manual_tab = st.tabs(["에이전트 추천안", "내가 고친 안"])
        with agent_tab:
            ui.caption("에이전트 추천안: " + card_summary(run.final))
            show_run(run, with_changes=True)
        with manual_tab:
            ui.caption("내가 고친 안: " + card_summary(manual.final))
            show_run(manual, with_changes=False, key="manual")

    # 직접 고쳐서 다시 확인
    st.subheader("직접 고쳐서 다시 확인")
    ui.caption("개최 월·장소·규모를 바꿔서 확인만 다시 해요. 자동으로 고치지는 않아요.")
    base = (manual or run).final  # 처음 값은 지금 카드(가장 최근 안)의 값
    places = screen.venue_choices(run)
    place_names = [screen.NO_VENUE, *[p["name"] for p in places]]
    current_place = base.venue[0].name if base.venue else screen.NO_VENUE
    scale_names = list(screen.SCALE_LABELS.values())
    with st.form("manual_form"):
        m1, m2, m3 = st.columns([350, 430, 308])
        with m1, st.container(key="check-field-month"):
            months = st.multiselect(
                "개최 월",
                list(range(1, 13)),
                default=base.timing.recommended_months,
                format_func=lambda m: f"{m}월",
            )
        with m2, st.container(key="check-field-place"):
            place = st.selectbox(
                "장소 (장소 후보 표에서)",
                place_names,
                index=place_names.index(current_place) if current_place in place_names else 0,
            )
        with m3, st.container(key="check-field-scale"):
            scale = st.radio(
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
                    manual = verify_idea(edited, request, tools(), max_fixes=0)  # 확인만
            except Exception as e:  # noqa: BLE001
                ui.error(str(e))
            else:
                reset_after("manual_run")  # 예전 기획서·홍보물도 지운다
                ss["manual_run"] = manual.model_dump(mode="json")
                st.rerun()

    # 어느 안으로 진행할지
    st.subheader("어느 안으로 진행할까요?")
    options = run_options()
    chosen_name = st.radio(
        "진행할 안", list(options), horizontal=True, label_visibility="collapsed"
    )
    chosen = options[chosen_name]
    if ss.get("approved") and ss["approved"] != chosen_name:
        # 진행할 안을 바꾸면 예전 안으로 만든 기획서·홍보물을 지운다 (다시 확인할 때는 reset_after)
        for key in ("approved", "plan", "plan_error", "plan_path", "promo"):
            ss.pop(key, None)
    ready = chosen.outcome == "ready_for_approval"
    if not ready:
        with st.container(key="check-blocked"):
            if chosen_name == "내가 고친 안":
                ui.warning(
                    "❌ 항목이 남아 있어 기획서를 만들 수 없어요. 다른 값을 바꿔서 다시 확인해보세요."
                )
            else:
                ui.warning(
                    "고쳐도 통과하지 못한 확인이 있어요. 직접 고쳐서 다시 확인하거나 다른 아이디어를 골라보세요."
                )
    if st.button("이대로 진행", type="primary", disabled=not ready, key="check-proceed"):
        if ss.get("approved") != chosen_name or "plan" not in ss:
            ss.pop("plan", None)
            ss.pop("plan_error", None)
            ss.pop("promo", None)  # 기획서를 다시 만들면 홍보물도 지운다
        ss["approved"] = chosen_name
        goto(4)


# ---------- ④ 기획서 ----------


def step_plan(request: UserRequest) -> None:
    plan_now = current_plan()
    approved_now = plan_now is not None and plan_now.status == "approved"
    st.html(style.head_html(4, "기획서를 최종 승인했어요" if approved_now else None))
    try:
        from agent.plan import (
            PlanGenerationError,
            approve_plan,
            generate_plan,
            plan_to_markdown,
            save_plan,
        )
    except ImportError:
        ui.info("기획서 기능 준비 중이에요.")
        return
    approved_run = run_options()[ss["approved"]]
    if "plan" not in ss:
        if error := ss.get("plan_error"):  # 지난번에 실패: 쉬운 이유 한 줄 + 다시 만들기
            ui.warning(error)
            if not st.button(screen.RETRY_PLAN_LABEL, type="primary", key="retry_plan"):
                return
        # 장소 후보를 기획서에 넘기는 방식은 A와 정할 예정. 지금은 고른 안의 확인 결과 그대로 넘긴다
        try:
            with st.spinner("기획서를 쓰는 중이에요…"):
                plan = generate_plan(approved_run, request, approved=True)
        except PlanGenerationError as e:
            ss["plan_error"] = screen.plan_failure_reason(e)
            st.rerun()  # 이유와 "다시 만들기" 버튼을 보여준다
        except Exception as e:  # noqa: BLE001
            ui.error(str(e))
            return
        md_path, _ = save_plan(plan)
        ss["plan"] = plan.model_dump(mode="json")
        ss["plan_path"] = str(md_path)
        ss.pop("promo", None)
        if ss.pop("plan_error", None):
            st.rerun()  # 다시 만들기에 성공하면 지난 실패 안내와 버튼을 지우고 다시 그린다
    plan = current_plan()
    doc, rail = st.columns([3, 1], gap="large")
    with rail, st.container(key="card-rail"):
        st.html(style.section_html("승인 전 확인" if plan.status != "approved" else "승인 완료"))
        state = "승인" if plan.status == "approved" else "승인 전"
        st.html(
            style.chips_html(
                [f"v{plan.version} {'승인본' if plan.status == 'approved' else '초안'}", state],
                light_from=1,
            )
        )
        ui.success(f"{ss['approved']}으로 기획서를 만들었어요.")
        if plan.is_synthetic:
            ui.warning("🧪 가상 데이터가 섞인 확인 결과로 만든 기획서예요.")
        ui.caption(f"저장: {ss.get('plan_path', '')}")
    with doc, st.container(key="doc"):
        ui.markdown(plan_to_markdown(plan))
    with rail:
        step_plan_actions(plan, approve_plan, save_plan)


def step_plan_actions(plan, approve_plan, save_plan) -> None:
    """기획서 오른쪽: 최종 승인 → 홍보물 만들러 가기."""
    if plan.status != "approved":
        ui.info("기획서를 최종 승인하면 홍보물을 만들 수 있어요.")
        if st.button("기획서 최종 승인", type="primary"):
            plan = approve_plan(plan)
            md_path, _ = save_plan(plan)  # 같은 파일 이름으로 승인본을 덮어쓴다
            ss["plan"] = plan.model_dump(mode="json")
            ss["plan_path"] = str(md_path)
            ss.pop("promo", None)
            goto(5)
    else:
        ui.success("기획서를 최종 승인했어요.")
        if st.button("홍보물 만들러 가기", type="primary"):
            goto(5)


# ---------- ⑤ 홍보물 ----------


def step_promo() -> None:
    """최종 승인한 기획서로 포스터 + SNS 글. 승인 전에는 이 단계에 올 수 없다."""
    from agent.plan import PlanNotApprovedError, require_approved
    from app import promo

    st.html(style.head_html(5))
    plan = current_plan()
    approved = plan is not None and plan.status == "approved"
    if st.button("홍보물 만들기", type="primary", disabled=not approved):
        try:
            require_approved(plan)
            with st.spinner("포스터와 SNS 글을 만드는 중이에요…"):
                from agent.proposals import default_llm

                result = promo.make_promo(
                    plan,
                    api_key=settings.llm_api_key.get_secret_value() or None,
                    image_model=settings.image_model or None,
                    text_model=settings.llm_model or None,  # 포스터 글자 검사에 쓰는 모델
                    llm=default_llm(),
                )
        except PlanNotApprovedError as e:
            ui.warning(str(e))
        except Exception as e:  # noqa: BLE001
            ui.error(str(e))
        else:
            ss["promo"] = result.model_dump(mode="json")
    if "promo" not in ss:
        return
    result = promo.PromoResult.model_validate(ss["promo"])
    if result.is_synthetic:
        ui.warning("🧪 가상 데이터가 섞인 기획서로 만든 홍보물이에요.")
    left, right = st.columns([2, 3], gap="large")
    with left, st.container(key="card-poster"):
        st.image(result.poster_path, caption="포스터 미리보기 (1200×1600)")
        with open(result.poster_path, "rb") as f:
            st.download_button(
                "포스터 내려받기", f.read(), file_name="poster.png", mime="image/png"
            )
        if result.poster_mode == "ai_text":
            ui.caption("AI가 정한 문구만 포스터에 그렸는지 글자를 읽어 확인했어요.")
        if result.image_cropped:
            ui.caption("받은 그림이 세로 3:4가 아니어서 1200×1600에 맞췄어요.")
    with right, st.container(key="card-sns"):
        if result.image_notice:
            ui.warning(result.image_notice)
            ui.caption("그림 설명 (그대로 복사해 쓰세요)")
            st.code(result.image_prompt, language=None)
            ui.caption("포스터 문구")
            st.code("\n".join((result.poster_lines or result.poster_text).values()), language=None)
        ui.markdown("**SNS 글 (인스타그램)**")
        if result.sns_text:
            st.code(result.sns_text + "\n\n" + " ".join(result.hashtags), language=None)
        if result.sns_notice:
            ui.warning(result.sns_notice)
        ui.markdown("**정보 일치 검사** (기획서와 같은지)")
        for c in result.checks:
            ui.write(f"{'✅' if c.ok else '⚠️'} {c.item}: {c.detail}")


# ---------- 화면 ----------

if ss.pop("scroll_top", False):  # 단계가 바뀌면 맨 위부터 보이게
    components.html(
        "<script>window.parent.document.querySelectorAll('[data-testid=stMain], section.main, .main, "
        '[data-testid="stAppViewContainer"]\').forEach(e => e.scrollTo(0, 0));'
        "window.parent.scrollTo(0, 0);</script>",
        height=0,
    )

st.html(style.CSS)
with st.sidebar:
    st.html(style.sidebar_html(has_llm))

making = "idea_job" in ss and current_request() is not None
step = 2 if making else min(ss.get("step", 1), reachable_step())  # 갈 수 없는 단계면 앞으로 돌린다
ss["step"] = step
request = current_request()
st.html(style.nav_html(step))
with st.container(key="sr-only"):  # 화면 읽기 프로그램용 (눈에는 위 단계 탭과 칩으로 보인다)
    ui.write(
        "전국 축제 트렌드와 제주 데이터로 우리 동네 축제 아이디어를 만들고, 제주 데이터로 확인해요."
    )
    ui.markdown(screen.progress_text(step))
    if step >= 2 and request is not None:
        ui.caption(screen.selection_summary(request, current_card() if step >= 3 else None))
if step >= 2 and not making:
    back_button(step)

if making:
    make_ideas(request)
elif step == 1:
    step_request()
elif step == 2:
    step_ideas(request)
elif step == 3:
    step_check(request, current_card())
elif step == 4:
    step_plan(request)
else:
    step_promo()
footer()
