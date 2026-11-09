"""화면(B)이 부르는 아이디어 제안 진입점.

- propose_ideas: 기존 뉴스 사례 기반 흐름 (v1 계약). 회의에서 뉴스 모듈 정리 후 없앤다
- propose_idea_cards: 새 설계(트렌드 × 제주 재료) 흐름 (v2 초안 계약, agent/draft_contracts.py)
"""

from pydantic import BaseModel, Field

from agent import draft_contracts as v2
from agent.demo import demo_cases, demo_ideas
from agent.demo_cards import demo_proposal
from agent.idea_cards import CardGenerationError, generate_idea_cards
from agent.idea_gen import TrendData
from agent.ideas import IdeaGenerationError
from agent.llm import LLMClient
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


def propose_idea_cards(
    request: v2.UserRequest,
    *,
    demo: bool = True,
    llm: LLMClient | None = None,
    data: TrendData | None = None,
) -> v2.IdeaProposal:
    """사용자 조건으로 아이디어 카드 3장을 제안한다 (새 설계).

    demo=True: 기획서 9-2 "애월 감귤" 예시 카드를 준다. 입력 조건과 상관없이 같은 카드다.
    demo=False: 문체부 패널로 후보를 만들고 llm이 3개를 고른다. llm이 없으면 CardGenerationError.
    data를 넘기지 않으면 data/processed/의 축제 패널을 읽는다.
    """
    if demo:
        return demo_proposal()
    if llm is None:
        raise CardGenerationError("AI 공급자가 아직 연결 전이에요. 지금은 데모로 확인해주세요.")
    if data is None:
        from research.trends import load_panel

        try:
            data = TrendData.from_panel(load_panel())
        except FileNotFoundError as exc:
            raise CardGenerationError(str(exc)) from exc
    return generate_idea_cards(request, data, llm)
