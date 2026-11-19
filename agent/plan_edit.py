"""사용자가 수정한 Markdown을 보관하고 홍보물에 필요한 값을 동기화한다."""

import re

from agent.draft_contracts import PLAN_TEXT_SECTIONS, FestivalPlan, PlanProgram
from agent.plan import plan_to_markdown


def edit_plan(plan: FestivalPlan, markdown: str) -> FestivalPlan:
    source = markdown.strip()
    if not source:
        raise ValueError("기획서 내용을 입력해주세요.")
    if source == plan_to_markdown(plan).strip():
        return plan
    headings = list(re.finditer(r"(?m)^##\s+(?:\d+\.\s*)?(.+?)\s*$", source))
    sections = {
        h[1].strip(): source[h.end():headings[i + 1].start() if i + 1 < len(headings) else len(source)].strip()
        for i, h in enumerate(headings)
    }
    required = ["사업 개요", "세부 프로그램 (제안)", *[title for _, title in PLAN_TEXT_SECTIONS]]
    missing = [title for title in required if title not in sections]
    if missing:
        raise ValueError("다음 항목 제목을 유지해주세요: " + ", ".join(missing))
    overview_rows = {}
    for line in sections["사업 개요"].splitlines():
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 2:
                overview_rows[cells[0]] = cells[1]
    fields = {"축제명": "name", "기간": "period", "지역": "region", "장소": "venue",
              "대상": "target", "목적": "purpose", "주최·주관": "organizer"}
    if any(not overview_rows.get(label) for label in fields):
        raise ValueError("사업 개요 표의 축제명·기간·지역·장소·대상·목적·주최·주관 칸을 유지해주세요. 모르는 값은 미확인으로 적어주세요.")
    programs = []
    for line in sections["세부 프로그램 (제안)"].splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"\s*-\s+\*\*(.+?)\*\*\s*[:：]\s*(.+)", line)
        if not match:
            raise ValueError("프로그램은 '- **프로그램 이름**: 설명' 형식으로 적어주세요.")
        programs.append(PlanProgram(name=match[1].strip(), description=match[2].strip()))
    overview = plan.overview.model_copy(update={field: overview_rows[label] for label, field in fields.items()})
    data = plan.model_dump()
    data.update(
        version=plan.version + 1, status="draft", approved_at=None,
        title=overview.name, overview=overview.model_dump(),
        sections=[s.model_copy(update={"body": sections[s.title]}).model_dump() for s in plan.sections],
        programs=[p.model_dump() for p in programs], markdown_override=source + "\n",
    )
    return FestivalPlan.model_validate(data)
