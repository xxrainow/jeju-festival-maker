"""화면(B)이 부르는 아이디어 제안 진입점.

지금은 데모 응답만 준다. 실제 검색(Tavily)과 LLM(Gemini 예정)이 붙어도
화면 쪽 호출 코드(propose_ideas)와 돌려주는 모양(IdeaProposal)은 그대로 둔다.
"""

from pydantic import BaseModel, Field

from agent.demo import demo_cases, demo_ideas
from agent.ideas import IdeaGenerationError
from schemas.contracts import FestivalCase, FestivalIdea, UserRequest

DEMO_NOTICE = "데모 응답이에요. 사례와 아이디어는 모두 가상 자료이며 실제 검색 결과가 아니에요."
DRAFT_NOTICE = "데이터 검토 전 아이디어예요. 제주 데이터와 운영 조건을 확인한 뒤 다듬어요."


class IdeaProposal(BaseModel):
    """아이디어 카드 화면에 필요한 것 한 묶음."""

    request: UserRequest
    cases: list[FestivalCase]  # 아이디어가 인용한 사례. 카드의 "참고 사례" 출처 표시에 쓴다
    ideas: list[FestivalIdea]  # 정확히 3개
    is_demo: bool  # True면 화면에 DEMO_NOTICE를 꼭 보여준다
    notices: list[str] = Field(default_factory=list)  # 화면에 그대로 보여줄 안내 문장

    def cases_for(self, idea: FestivalIdea) -> list[FestivalCase]:
        """아이디어가 인용한 사례만 순서대로 돌려준다."""
        by_id = {case.case_id: case for case in self.cases}
        return [by_id[cid] for cid in idea.case_ids if cid in by_id]


def propose_ideas(request: UserRequest, *, demo: bool = True) -> IdeaProposal:
    """사용자 조건으로 축제 아이디어 3개를 제안한다.

    demo=True: 네트워크와 API 키 없이 가상 응답을 준다 (화면 연결·시연 연습용).
    demo=False: 실제 검색과 LLM 생성. 아직 연결 전이라 IdeaGenerationError를 던진다.
    """
    if not demo:
        raise IdeaGenerationError(
            "실제 사례 검색과 AI 아이디어 생성은 아직 연결 전이에요. 지금은 데모로 확인해주세요."
        )
    return IdeaProposal(
        request=request,
        cases=demo_cases(),
        ideas=demo_ideas(),
        is_demo=True,
        notices=[DEMO_NOTICE, DRAFT_NOTICE],
    )
