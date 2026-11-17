"""생성 문장의 지역·예산 조건 검사. 외부 사례 인용은 호출부에서 제외한다."""

import re

from agent.draft_contracts import UserRequest


def foreign_regions(text: str, region: str | None) -> list[str]:
    if not region:
        return []
    from analytics.flow_spec import EMD_CODES

    found = []
    for area in EMD_CODES.values():
        if area == region:
            continue
        short = area.split()[-1]
        core = re.sub(r"(읍|면|동)$", "", short)
        # 읍면동 접미사를 생략한 축제명과 섬 이름도 검사한다.
        aliases = {short, core}
        if short in ("추자면", "우도면"):
            aliases.add(core + "도")
        # 같은 이름의 동이 있는 경우 전체 행정구역을 함께 구별한다.
        if any(a in text and a not in region for a in aliases if len(a) >= 2):
            found.append(short)
    return found


def expensive_program(text: str, constrained: bool) -> bool:
    # 실제 견적이 없는 소규모·예산 미정 기획에서는 장비 중심 공연을 확정 제안하지 않는다.
    return constrained and bool(re.search(r"드론\s*(?:쇼|공연|군집)|불꽃\s*(?:쇼|놀이|공연)", text))


def check_request_text(text: str, request: UserRequest, *, constrained: bool) -> str | None:
    if names := foreign_regions(text, request.region):
        return f"희망 지역과 다른 지역 이름이 있어요: {', '.join(names)}. 희망 지역 안에서 작성하세요."
    if expensive_program(text, constrained):
        return "예산·견적이 확인되지 않은 드론 쇼나 불꽃 공연 대신 기존 조명·산책 등으로 구성하세요."
    return None
