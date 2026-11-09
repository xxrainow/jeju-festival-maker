"""화면(B)이 부르는 아이디어 제안 진입점 (트렌드 × 제주 재료).

계약은 합의 전까지 agent/draft_contracts.py의 v2 초안을 쓴다.
"""

from agent import draft_contracts as v2
from agent.demo_cards import demo_proposal
from agent.idea_cards import CardGenerationError, generate_idea_cards
from agent.idea_gen import TrendData
from agent.llm import LLMClient


def propose_idea_cards(
    request: v2.UserRequest,
    *,
    demo: bool = True,
    llm: LLMClient | None = None,
    data: TrendData | None = None,
) -> v2.IdeaProposal:
    """사용자 조건으로 아이디어 카드 3장을 제안한다.

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
