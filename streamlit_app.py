"""제주 축제 메이커 화면 (docs/a-guide.md 순서). 한 번에 한 단계만 보여준다.

① 조건 입력 → ② 아이디어 → ③ 데이터로 확인 → ④ 기획서 → ⑤ 홍보물
지금 단계는 session_state["step"]. 앞 단계로 돌아가서 값을 바꾸면 뒤 단계 결과는 지운다 (reset_after).
st.session_state에는 모델을 model_dump(mode="json")로 저장하고 model_validate로 읽는다.
"""

from importlib import reload
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from agent.draft_contracts import IdeaProposal, UserRequest, VerificationRun
from analytics.flow_spec import EMD_CODES
from app import screen, style
from app.settings import Settings

# 스타일 파일 수정은 서버 재시작 없이 이번 실행부터 반영한다.
reload(style)


class _EscapedText:
    """st.markdown/write/caption/info/warning/error/success에 넘기는 문장의 "~"를 이스케이프한다 (취소선 방지)."""

    def __getattr__(self, name):
        fn = getattr(st, name)

        def call(*args, **kwargs):
            return fn(*(screen.md(a) for a in args), **kwargs)

        return call


ui = _EscapedText()

st.set_page_config(
    page_title="제주 축제 메이커",
    page_icon=str(Path(__file__).resolve().parent / "assets" / "brand-mark.png"),
    layout="wide",
    initial_sidebar_state="collapsed",
)
settings = Settings()
has_llm = bool(settings.llm_api_key.get_secret_value())
AREAS = sorted(EMD_CODES.values())
TOOLS_NOTE = "확인 도구 5개를 돌리는 중이에요…"
ss = st.session_state


# ---------- 공통 ----------


def footer(*, show_evidence: bool = False) -> None:
    if show_evidence:
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
        "check_choice",
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


def current_choice() -> str:
    """지금 보여주고 고를 안: 마지막으로 고른 안 → 진행한 안 → 에이전트 추천안 순서."""
    options = run_options()
    for name in (ss.get("check_choice"), ss.get("approved")):
        if name in options:
            return name
    return "에이전트 추천안"


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


def fill_demo_conditions() -> None:
    """시연을 켤 때만 기본 조건을 채운다. 제출 전 수정한 값은 그대로 사용한다."""
    if not ss.get("use_demo"):
        return
    from agent.demo_cards import DEMO_REQUEST

    ss["draft"] = DEMO_REQUEST.model_dump(mode="json")
    ss["draft_from_ai"] = False
    ss.pop("notes", None)
    ss.pop("parse_error", None)


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

    # 폼 밖에서 즉시 반영해야 채워진 조건을 제출 전에 확인할 수 있다.
    with st.expander("시연 옵션"):
        use_demo = st.checkbox(
            screen.DEMO_TOGGLE_LABEL, key="use_demo", on_change=fill_demo_conditions
        )
        if use_demo:
            ui.caption(
                "애월·겨울·감귤·가족·1,000만 원 조건을 채웠어요. "
                "아래에서 확인·수정한 뒤 ‘아이디어 보기’를 눌러주세요. AI는 사용하지 않아요."
            )

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


def stage_navigation(step: int) -> None:
    """완료한 단계 탭으로 돌아간다. 앞으로의 단계는 이동할 수 없다."""
    with st.container(key="idea-nav", horizontal=True,
                      horizontal_alignment="distribute", vertical_alignment="center"):
        st.html(style.logo_html(), width="content")
        with st.container(key="idea-step-tabs", width="content", horizontal=True,
                          vertical_alignment="center", gap=None):
            for i, name in enumerate(screen.STEPS, start=1):
                if st.button(
                    f"{i:02d} {name}", key=f"nav_{i}",
                    type="primary" if i == step else "tertiary",
                    disabled=i >= step,
                    help=f"{name} 단계로 돌아갑니다" if i < step else None,
                ):
                    goto(i)
        st.html('<span class="fl-nav-balance"></span>', width="content")


def step_ideas(request: UserRequest) -> None:
    st.html(style.head_html(2))
    with st.container(key="idea-conditions", horizontal=True, vertical_alignment="center"):
        st.html(style.request_chips(request), width="content")  # 조건 입력으로는 상단 01 탭으로 돌아간다
    if conflict := screen.season_conflict(request):
        ui.warning(f"⚠️ {conflict}")
    proposal = IdeaProposal.model_validate(ss["proposal"])
    if proposal.is_demo:
        diffs = screen.demo_differences(proposal, request)
        with st.container(key="idea-demo-notice"), st.expander("예시 카드예요", expanded=False):
            ui.markdown(screen.demo_warning_text(ss.get("demo_reason"), diffs))
            for notice in proposal.notices:
                ui.write(notice)
    else:
        for notice in proposal.notices:
            ui.info(notice)

    with st.container(key="idea-cards"):
        cols = st.columns(3)
        for col, card in zip(cols, proposal.ideas, strict=True):  # rank 순서, rank·score는 숨김
            with col, st.container(key=f"card-idea-{card.idea_id}"):
                st.html(style.idea_card_head_html(card))  # 형식 칩 + 형식 아이콘
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
    for row_index, row in enumerate((results[:2], results[2:])):
        with st.container(key=f"check-row-{key}-{row_index}"):
            cols = st.columns(len(row))
            for col, r in zip(cols, row, strict=True):
                with col, st.container(key=f"res-{r.status}-{key}-{r.check}"):
                    summary = screen.check_card_summary(r)
                    st.html(style.check_head_html(screen.CHECK_LABELS[r.check], r.status, False))
                    ui.write(summary["reason"])
                    if r.check == "check_timing" and with_changes and (notice := screen.season_notice(run)):
                        ui.write(f"⚠️ {notice}")  # 에이전트가 입력 계절 밖 달로 바꿨을 때
                    st.html(style.check_metric_html(summary))
                    if summary["warning"]:
                        st.html(style.check_warning_html(summary["warning"]))
                    rows = screen.venue_table(r) if r.check == "check_venue" else []
                    # 장소 후보 표는 펼쳐야 보이므로, 후보가 있다는 걸 문구에서 바로 알린다
                    detail_label = (
                        f"장소 후보 {len(rows)}곳 비교·근거 보기" if rows else "상세 결과와 근거 보기"
                    )
                    with st.expander(detail_label):
                        ui.write(r.reason)
                        for line in screen.key_numbers(r):
                            ui.caption(line)
                        if rows:
                            st.dataframe(pd.DataFrame(rows), hide_index=True)
                        if r.sources:
                            ui.caption("출처: " + " · ".join(r.sources))
                        other_warnings = [w for w in r.warnings if w != summary["warning"]]
                        if other_warnings:
                            ui.markdown("**추가로 확인할 점**")
                            for warning in other_warnings:
                                ui.write(f"- {warning}")
    if not with_changes:
        return
    # 확인 과정과 바뀐 점을 한 타임라인으로: 처음 확인 → 바꾼 점 → 다시 확인 …
    st.subheader("확인 과정과 바뀐 점")
    changes = screen.friendly_changes(run)
    with st.container(key=f"timeline-{key}"):
        for rd in run.rounds:
            st.html(style.round_row_html(screen.round_status_row(rd), last=rd is run.rounds[-1]))
            for j, ch in enumerate(c for c in changes if c["round"] == rd.round):
                with st.container(key=f"chg-{key}-{rd.round}-{j}"):
                    ui.markdown(f"**{ch['title']}**")
                    ui.write(ch["reason"])
                    if ch["note"]:
                        ui.write(f"⚠️ {ch['note']}")
                    if ch["low_data"]:
                        ui.write(
                            f"⚠️ {screen.LOW_DATA_NOTICE}. " + ", ".join(ch["low_data"]) + "."
                        )
                    for n in ch["numbers"]:
                        ui.caption(n)
                    if ch["season"]:
                        ui.caption(ch["season"])
        if not changes:
            ui.caption("에이전트가 바꾼 점은 없어요.")


def step_check(request: UserRequest, card) -> None:
    with st.container(key="verification"):
        verification_content(request, card)


def verification_content(request: UserRequest, card) -> None:
    st.html(style.head_html(3))
    st.html(style.check_selection_html(card))
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

    def strip(name: str, r: VerificationRun) -> None:
        st.html(style.plan_strip_html(name, r.final, r.outcome == "ready_for_approval"))

    if manual is None:
        strip("에이전트 추천안", run)
        show_run(run, with_changes=True)
    else:
        # 방금 직접 고쳐서 다시 확인했으면 그 결과 탭을 먼저 연다
        agent_tab, manual_tab = st.tabs(
            ["에이전트 추천안", "내가 고친 안"], default=current_choice()
        )
        with agent_tab:
            strip("에이전트 추천안", run)
            show_run(run, with_changes=True)
        with manual_tab:
            strip("내가 고친 안", manual)
            show_run(manual, with_changes=False, key="manual")

    # 직접 고쳐서 다시 확인
    st.subheader("직접 고쳐서 다시 확인")
    with st.container(key="check-manual-intro"):  # 안내 두 줄은 붙여서 한 덩어리로
        ui.caption("개최 월·장소·규모를 바꿔서 확인만 다시 해요. 자동으로 고치지는 않아요.")
        ui.caption("개최 월을 여러 개 고르면 각 달을 모두 확인해요. 하나라도 실패하면 그 안으로는 진행할 수 없어요.")
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
                "장소 (위 장소 카드의 후보 중에서)",
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
                ss["check_choice"] = "내가 고친 안"  # 다시 확인한 안을 바로 보여주고 고른 상태로
                st.rerun()

    # 어느 안으로 진행할지
    st.subheader("어느 안으로 진행할까요?")
    options = run_options()
    names = list(options)
    # key 없이 index로만 정한다: 단계를 오가도 check_choice 기준으로 다시 그려진다
    chosen_name = st.radio(
        "진행할 안", names, index=names.index(current_choice()),
        horizontal=True, label_visibility="collapsed",
    )
    ss["check_choice"] = chosen_name
    chosen = options[chosen_name]
    if ss.get("approved") and ss["approved"] != chosen_name:
        # 진행할 안을 바꾸면 예전 안으로 만든 기획서·홍보물을 지운다 (다시 확인할 때는 reset_after)
        for key in ("approved", "plan", "plan_error", "plan_path", "promo"):
            ss.pop(key, None)
    ready = chosen.outcome == "ready_for_approval"
    if not ready:
        with st.container(key="check-blocked"):
            failed_labels = [
                screen.CHECK_LABELS[r.check]
                for r in chosen.rounds[-1].results if r.status == "fail"
            ]
            ui.warning(
                "❌ " + "·".join(failed_labels) + " 확인을 통과하지 못해 진행을 멈췄어요. "
                "아래 이유와 수정 방법을 확인해주세요."
            )
            for i, line in enumerate(screen.blocked_check_guidance(chosen)):
                if line.startswith(("**이렇게 바꿔보세요:**", "**수정 제안:**")):
                    with st.container(key=f"check-blocked-fix-{i}"):  # 수정 방법은 강조 상자
                        ui.markdown(line)
                else:
                    ui.markdown(line)
            if chosen_name == "내가 고친 안" and run.outcome == "ready_for_approval":
                ui.caption(
                    "다시 수정하지 않고 진행하려면 위 ‘진행할 안’에서 "
                    "‘에이전트 추천안’을 선택하세요. 추천안의 조건으로 기획서를 만들어요."
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
        )
        from app import plan_view

        reload(plan_view)
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
        ss["plan"] = plan.model_dump(mode="json")
        ss.pop("plan_path", None)
        ss.pop("promo", None)
        if ss.pop("plan_error", None):
            st.rerun()  # 다시 만들기에 성공하면 지난 실패 안내와 버튼을 지우고 다시 그린다
    plan = current_plan()
    with st.container(key="plan-layout"):
        doc, rail = st.columns([896, 320], gap="large")
        with doc, st.container(key="doc"):
            preview_tab, edit_tab = st.tabs(["Preview", "Edit"])
            source = plan_to_markdown(plan)
            editor_key = f"plan_markdown_{plan.plan_id}_{plan.version}"
            with preview_tab:
                st.html(plan_view.document_html(plan))
            with edit_tab:
                st.caption("마크다운으로 수정할 수 있어요. 항목 제목과 표 형식을 유지한 뒤 적용해주세요.")
                edited = st.text_area("기획서 Markdown", value=source, height=720, key=editor_key,
                                      label_visibility="collapsed")
                save_col, download_col, json_col = st.columns(3)
                with save_col:
                    if st.button("수정 내용 적용", type="primary", key="save_plan_markdown"):
                        from agent.plan_edit import edit_plan

                        try:
                            revised = edit_plan(plan, edited)
                        except ValueError as error:
                            st.error(str(error))
                        else:
                            ss["plan"] = revised.model_dump(mode="json")
                            ss.pop("promo", None)
                            ss["plan_edit_saved"] = True
                            st.rerun()
                with download_col:
                    st.download_button(".md 다운로드", data=source,
                                       file_name=f"{plan.plan_id}_v{plan.version}.md",
                                       mime="text/markdown", key="download_plan_markdown",
                                       disabled=edited.strip() != source.strip(), use_container_width=True)
                with json_col:
                    st.download_button(".json 다운로드", data=plan.model_dump_json(indent=2),
                                       file_name=f"{plan.plan_id}_v{plan.version}.json",
                                       mime="application/json", key="download_plan_json",
                                       disabled=edited.strip() != source.strip(), use_container_width=True)
                if ss.pop("plan_edit_saved", False):
                    st.success("수정 내용을 적용했어요. Preview에서 확인해주세요. 파일은 다운로드 버튼으로 받을 수 있어요.")
            has_unsaved = edited.strip() != source.strip()
        with rail, st.container(key="card-rail"):
            st.html(plan_view.rail_html(plan, ss["approved"]))
            step_plan_actions(plan, approve_plan, has_unsaved=has_unsaved)


@st.cache_data(show_spinner=False)
def plan_download_files(markdown: str) -> tuple[bytes, bytes]:
    from app.plan_export import to_docx, to_hwpx

    return to_docx(markdown), to_hwpx(markdown)


def step_plan_actions(plan, approve_plan, *, has_unsaved=False) -> None:
    """기획서 오른쪽: 최종 승인 → 홍보물 만들러 가기."""
    if has_unsaved:
        st.info("Edit의 수정 내용을 적용한 뒤 진행해주세요.")
    from agent.plan import plan_to_markdown

    docx, hwpx = plan_download_files(plan_to_markdown(plan))
    with st.container(key="plan-downloads"):
        st.html('<div class="fl-plan-download-title">파일로 저장하기</div>')
        word_col, hangul_col = st.columns(2, gap="small")
        name = f"{plan.plan_id}_v{plan.version}"
        word_col.download_button(
            "Word (.docx)", data=docx, file_name=f"{name}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            disabled=has_unsaved, use_container_width=True, key="download_plan_docx",
        )
        hangul_col.download_button(
            "한글 (.hwpx)", data=hwpx, file_name=f"{name}.hwpx",
            mime="application/hwp+zip", disabled=has_unsaved,
            use_container_width=True, key="download_plan_hwpx",
        )

    st.html('<hr class="fl-plan-approve-divider">')
    if plan.status != "approved":
        if st.button("기획서 최종 승인", type="primary", use_container_width=True, disabled=has_unsaved):
            plan = approve_plan(plan)
            ss["plan"] = plan.model_dump(mode="json")
            ss.pop("promo", None)
            goto(5)
    else:
        ui.success("기획서를 최종 승인했어요.")
        if st.button("홍보물 만들러 가기", type="primary", use_container_width=True, disabled=has_unsaved):
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
    with st.container(key="promo"):
        promo_content(plan, result)


def promo_content(plan, result) -> None:
    """Figma 05: 왼쪽 포스터, 오른쪽 그림 안내 · SNS 글 · 정보 일치 검사 · 저장."""
    from app import promo

    if result.is_synthetic:
        with st.container(key="promo-notice-synthetic"):
            ui.warning("가상 데이터가 섞인 기획서로 만든 홍보물이에요.")
    left, right = st.columns([2, 3], gap="large")
    with left:
        with st.container(key="card-poster"):
            st.image(result.poster_path)
        ui.caption("포스터 미리보기 (1200×1600)")
        with open(result.poster_path, "rb") as f:
            st.download_button(
                "포스터 내려받기", f.read(), file_name="poster.png", mime="image/png",
                key="poster-download",
            )
        if result.poster_mode == "ai_text":
            ui.caption("AI가 정한 문구만 포스터에 그렸는지 글자를 읽어 확인했어요.")
        if result.image_cropped:
            ui.caption("받은 그림이 세로 3:4가 아니어서 1200×1600에 맞췄어요.")
    with right:
        if result.image_notice:
            with st.container(key="promo-notice-image"):
                ui.warning(result.image_notice)
            with st.expander("그림 설명과 포스터 문구 보기 (그대로 복사해 쓰세요)"):
                ui.caption("그림 설명")
                st.code(result.image_prompt, language=None)
                ui.caption("포스터 문구")
                st.code(
                    "\n".join((result.poster_lines or result.poster_text).values()), language=None
                )
        sns = promo.sns_copy_text(result)
        with st.container(key="card-sns"):
            st.html(style.sns_head_html(len(sns) if sns else None))
            if sns:
                st.html(style.sns_body_html(sns))
                components.html(style.copy_button_html(sns), height=48)
            if result.sns_notice:
                ui.warning(result.sns_notice)
        with st.container(key="card-checks"):
            st.html(style.promo_checks_html(result.checks))
        save_col, zip_col = st.columns(2)
        if save_col.button("＋ 포스터 · SNS 문구 저장", type="primary", key="promo-save",
                           use_container_width=True):
            saved = promo.save_promo_files(result)
            ui.success("저장했어요: " + ", ".join(str(p) for p in saved))
        if plan is not None:
            from agent.plan import plan_to_markdown

            data = promo.promo_zip_bytes(result, plan_to_markdown(plan))
            zip_col.download_button(
                "기획서와 함께 ZIP으로 저장", data,
                file_name=f"{promo.promo_stem(result)}_promo.zip", mime="application/zip",
                key="promo-zip", use_container_width=True,
                on_click=promo.save_promo_zip, args=(result, data),
            )
        st.html(style.promo_files_html(has_sns=bool(sns)))
        st.html(style.promo_info_html())


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
if step >= 2 and not making:
    stage_navigation(step)
else:
    st.html(style.nav_html(step))
with st.container(key="sr-only"):  # 화면 읽기 프로그램용 (눈에는 위 단계 탭과 칩으로 보인다)
    ui.write(
        "전국 축제 트렌드와 제주 데이터로 우리 동네 축제 아이디어를 만들고, 제주 데이터로 확인해요."
    )
    ui.markdown(screen.progress_text(step))
    if step >= 2 and request is not None:
        ui.caption(screen.selection_summary(request, current_card() if step >= 3 else None))

if making:
    make_ideas(request)
elif step == 1:
    step_request()
elif step == 2:
    with st.container(key="ideas"):
        step_ideas(request)
elif step == 3:
    step_check(request, current_card())
elif step == 4:
    with st.container(key="plan"):
        step_plan(request)
else:
    step_promo()
footer(show_evidence=step == 2 and not making)
