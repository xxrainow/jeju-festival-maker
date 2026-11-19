"""04 기획서의 문서형 HTML. 실제 기획안 값을 사용하고 외부 문장은 이스케이프한다."""

import re
from html import escape

from agent.draft_contracts import UNCONFIRMED, FestivalPlan, PlanKPI
from agent.plan import build_limitations, krw_text, plan_to_markdown, plan_warning_notes
from app import screen, style


def _text(value) -> str:
    return escape(str(value if value is not None else UNCONFIRMED))


def _prose(value: str) -> str:
    paragraphs = []
    for paragraph in value.split("\n\n"):
        if paragraph.strip():
            safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _text(paragraph.strip()))
            paragraphs.append(f'<p>{safe.replace(chr(10), "<br>")}</p>')
    return '<div class="fl-plan-copy">' + "".join(paragraphs) + "</div>"


def _table(headers, rows, kind="") -> str:
    def cell(value, column):
        content = _text(value)
        if kind == "budget" and column == 1 and value == UNCONFIRMED:
            content = f'<span class="fl-tag warn">{content}</span>'
        return f"<td>{content}</td>"

    return (
        f'<div class="fl-plan-table {kind}"><table><thead><tr>'
        + "".join(f'<th scope="col">{_text(h)}</th>' for h in headers)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(cell(c, i) for i, c in enumerate(row)) + "</tr>" for row in rows)
        + "</tbody></table></div>"
    )


def _section(number: int, title: str, body: str, kind: str | None = None) -> str:
    tag = style.tag_html(kind) if kind else ""
    return (
        f'<section class="fl-plan-section" aria-labelledby="plan-section-{number}">'
        f'<h2 id="plan-section-{number}">{number}. {_text(title)}{tag}</h2>{body}</section>'
    )


def _kpi(kpi: PlanKPI) -> str:
    pending = style.tag_html("데이터 대기")
    baseline_pending = kpi.baseline.value is None
    target_pending = kpi.target.range is None
    baseline = _text(kpi.baseline.source) if baseline_pending else _text(kpi.baseline.value)
    target = (
        "근거 후보: " + _text(", ".join(kpi.target.basis) or "아직 없어요")
        if target_pending else _text(kpi.target.range)
    )
    return (
        '<article class="fl-plan-kpi"><div class="fl-plan-kpi-head">'
        f'<h3>{_text(kpi.metric)}</h3><small>{_text(kpi.region or "지역 미확인")}</small></div>'
        f'<p class="fl-plan-formula">계산: {_text(kpi.formula)}</p>'
        '<div class="fl-plan-kpi-values">'
        f'<div><div class="fl-plan-kpi-label">기준값 {pending if baseline_pending else ""}</div>'
        f'<p>{baseline}</p></div>'
        f'<div><div class="fl-plan-kpi-label">목표치 {pending if target_pending else ""}</div>'
        f'<p>{target}</p></div></div></article>'
    )


def _markdown_sections(source: str) -> dict[str, str]:
    headings = list(re.finditer(r"(?m)^##\s+(?:\d+\.\s*)?(.+?)\s*$", source))
    return {
        h[1].strip(): source[h.end():headings[i + 1].start() if i + 1 < len(headings) else len(source)].strip()
        for i, h in enumerate(headings)
    }


def _apply_markdown_edits(html: str, plan: FestivalPlan) -> str:
    """구조화된 값은 기존 UI로, 그 밖의 Markdown 수정은 같은 섹션 안에 표시한다."""
    if plan.markdown_override is None:
        return html
    from markdown_it import MarkdownIt

    original = _markdown_sections(plan_to_markdown(plan.model_copy(update={"markdown_override": None})))
    edited = _markdown_sections(plan.markdown_override)
    titles = ["사업 개요", "추진 배경·필요성", "목표·KPI", "기본 컨셉", "세부 프로그램 (제안)",
              "추진 일정", "예산 계획", "홍보 계획", "운영 계획", "위험 관리", "기대효과",
              "데이터 검증 결과 요약", "참고 사례", "성과 측정 방법", "가정과 한계", "데이터 출처"]
    kinds = {1: "overview", 7: "budget", 12: "checks", 13: "reference", 15: "limitations", 16: "sources"}
    renderer = MarkdownIt("commonmark", {"html": False}).enable("table")
    for number, title in enumerate(titles, 1):
        if title not in edited or edited[title] == original.get(title):
            continue
        body = renderer.render(edited[title])
        kind = kinds.get(number, "")
        body = body.replace("<table>", f'<div class="fl-plan-table {kind}"><table>')
        body = body.replace("</table>", "</table></div>")
        body = '<div class="fl-plan-copy">' + body + "</div>"
        pattern = rf'(<section class="fl-plan-section" aria-labelledby="plan-section-{number}"><h2[^>]*>.*?</h2>).*?(</section>)'
        html = re.sub(pattern, lambda m, content=body: m[1] + content + m[2], html, flags=re.DOTALL)
    return html


def document_html(plan: FestivalPlan) -> str:
    overview, budget, idea = plan.overview, plan.budget, plan.idea
    sections = {s.key: s.body for s in plan.sections}
    notes = plan_warning_notes(plan.checks)
    approved = plan.status == "approved"
    version = f"v{plan.version} {'승인본' if approved else '초안'}"
    chips = [overview.period, overview.region or "제주 전역", overview.target or "대상 미확인",
             f"예산 {krw_text(overview.budget_krw)}"]
    parts = [
        '<article class="fl-plan-document">',
        f'<span class="fl-plan-version{ " approved" if approved else "" }">{_text(version)}</span>',
        f'<h1>{_text(plan.title)} 기획서</h1>',
        '<div class="fl-plan-chips">'
        + "".join(f'<span>{_text(c)}</span>' for c in chips) + "</div>",
    ]
    summary = _table(["항목", "내용"], [
        ("축제명", overview.name), ("기간", overview.period),
        ("지역", overview.region or "제주 전역"), ("장소", overview.venue),
        ("대상", overview.target or UNCONFIRMED), ("예산", krw_text(overview.budget_krw)),
        ("목적", overview.purpose or UNCONFIRMED), ("주최·주관", overview.organizer),
    ], "overview")
    hints = list(notes["timing"])
    if overview.venue == UNCONFIRMED:
        venue = next((c for c in plan.checks if c.check == "check_venue"), None)
        candidates = (venue.evidence.get("candidate_places") or []) if venue else []
        names = [p["name"] for p in candidates if isinstance(p, dict) and p.get("name")]
        hints.append(
            "장소는 아직 미확인이에요. "
            + ("·".join(names) + "은(는) 확인 도구가 찾은 후보예요. " if names else "")
            + "대관 조건과 정확한 개최일은 별도로 확인해요."
        )
    if hints:
        label = "시기 확인 참고" if notes["timing"] else "장소 확인 참고"
        summary += f'<aside class="fl-plan-timing"><b>{label}</b>' + "".join(
            f'<p>{_text(h)}</p>' for h in hints
        ) + "</aside>"
    parts += [
        _section(1, "사업 개요", summary),
        _section(2, "추진 배경·필요성", _prose(sections.get("background", "")), "에이전트 해석"),
        _section(3, "목표·KPI", "".join(_kpi(k) for k in plan.kpis)
                 or _prose("목적에 맞는 성과 지표는 데이터 확보 후 정해요."),
                 "데이터 대기" if any(k.baseline.value is None or k.target.range is None
                                  for k in plan.kpis) else "데이터"),
        _section(4, "기본 컨셉", _prose(sections.get("concept", "")), "에이전트 해석"),
        _section(5, "세부 프로그램 (제안)", '<div class="fl-plan-programs">' + "".join(
            '<div class="fl-plan-program">'
            f'<b>{_text(p.name)}</b><p>{_text(p.description)}</p><small>운영 시간 미확인</small></div>'
            for p in plan.programs
        ) + "</div>"),
        _section(6, "추진 일정", '<div class="fl-plan-schedule">' + "".join(
            '<div>' + f'<span class="{ "event" if s.when == "당일" else "" }">{_text(s.when)}</span>'
            f'<p>{_text(s.task)}</p></div>' for s in plan.prep_schedule
        ) + "</div>"),
    ]
    budget_rows = [
        ("예산 상한", krw_text(budget.input_krw), "사용자 입력"),
        ("같은 형식 예산 중간값", krw_text(budget.format_median_krw), budget.source),
        *[("비슷한 규모 사례", krw_text(e.budget_krw), e.name) for e in budget.small_examples],
        ("규모", budget.scale, "예산 확인 결과"),
        ("항목별 금액", budget.items, "견적 입력 필요" if budget.items == UNCONFIRMED else "입력한 견적"),
    ]
    parts += [
        _section(7, "예산 계획", _table(["항목", "값", "근거"], budget_rows, "budget"), "데이터"),
        _section(8, "홍보 계획", _prose(sections.get("promotion", "")), "에이전트 해석"),
        _section(9, "운영 계획", _prose(sections.get("operation", "")), "에이전트 해석"),
    ]
    risk_body = sections.get("risk", "")
    risk_notes = notes["risk"]
    risk_body = "\n".join(
        line for line in risk_body.splitlines()
        if line.strip().removeprefix("- ") not in risk_notes
        and line.strip() != "**확인 도구에서 확인한 운영 주의사항**"
    )
    risk = _prose(risk_body)
    if risk_notes:
        risk += '<aside class="fl-plan-risk-notes"><b>확인 결과에 따른 운영 유의사항</b><ul>' + "".join(
            f'<li>{_text(n)}</li>' for n in risk_notes
        ) + "</ul></aside>"
    results = [
        (screen.CHECK_LABELS[c.check], style.STATUS_WORD[c.status], c.reason)
        for c in plan.checks
    ]
    parts += [
        _section(10, "위험 관리", risk, "에이전트 해석"),
        _section(11, "기대효과", _prose(sections.get("expected", "")), "에이전트 해석"),
        _section(12, "데이터 검증 결과 요약", _table(["확인", "결과", "이유"], results, "checks")),
    ]
    trend = idea.evidence.trend
    reference = f'<h3>전략 · {_text(trend.strategy or idea.reference.type)}</h3>'
    if trend.interpretation:
        reference += _prose(trend.interpretation)
    if idea.reference.designated_festivals:
        reference += _prose("참고 축제: " + ", ".join(
            f"{f.name}({f.grade})" for f in idea.reference.designated_festivals
        ))
    if idea.existing_jeju_festivals:
        reference += _table(["기존 축제", "개최 월"], [
            (f.name, f"{f.month}월" if f.month else "개최 월 미확인")
            for f in idea.existing_jeju_festivals
        ], "reference")
    parts.append(_section(13, "참고 사례", reference))
    measure = _table(["지표", "측정 방법"], [(k.metric, k.measure_plan) for k in plan.kpis])
    if any(k.baseline.value is None or k.target.range is None for k in plan.kpis):
        measure += '<p class="fl-plan-caption">기준값과 목표치는 실제 자료를 확보한 뒤 정해요. 현재 수치 목표는 데이터 대기예요.</p>'
    parts.append(_section(14, "성과 측정 방법", measure))
    limits = []
    for value in build_limitations(idea, plan.checks):
        label, _, description = value.partition(":")
        limits.append((label, description.strip()))
    assumptions = '<h3>가정</h3><ul class="fl-plan-assumptions">' + "".join(
        f'<li>{_text(a)}</li>' for a in plan.assumptions
    ) + "</ul><h3>미확인 사항</h3>" + _prose(" · ".join(plan.unconfirmed) or "없음")
    assumptions += '<h3>한계</h3>' + _table(["분류", "확인할 한계"], limits, "limitations")
    parts += [
        _section(15, "가정과 한계", assumptions),
        _section(16, "데이터 출처", _table(["항목", "값", "출처"], [
            (e.label.replace("신설리프트", "신설 비율"), e.value, e.source) for e in plan.evidence
        ], "sources")),
        "</article>",
    ]
    return _apply_markdown_edits("".join(parts), plan)


def rail_html(plan: FestivalPlan, selected: str) -> str:
    approved = plan.status == "approved"
    state = "승인 완료" if approved else "승인 전 확인"
    intro = (
        "최종 승인한 기획서로 홍보물을 만들 수 있어요."
        if approved else "기획서를 최종 승인하면 이 내용으로 홍보물을 만들 수 있어요."
    )
    parts = [(f'<div class="fl-plan-rail-head"><small>{"APPROVED" if approved else "BEFORE APPROVE"}</small>'
              f'<h2>{state}</h2><p>{intro}</p></div>')]
    if plan.is_synthetic:
        parts.append('<div class="fl-plan-rail-note warning">' + style.check_icon_html("주의할 점")
                     + '<p>가상 데이터가 섞인 확인 결과로 만든 기획서예요. 실제 판단 전에 실데이터로 다시 확인해야 해요.</p></div>')
    parts.append('<div class="fl-plan-rail-note success">' + style.check_icon_html("주의할 점")
                 + f'<p>{_text(selected)}으로 기획서를 만들었어요.</p></div>')
    return "".join(parts)
