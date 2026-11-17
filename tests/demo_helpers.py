"""B 화면 테스트용 12월 데모 카드.

실제 데모 카드 1은 시연용으로 추천 1월이다 (애월에서 시기 실패 → 12월로 수정).
화면 테스트는 원래 "대정읍 12월 → 11월" 흐름을 기준으로 쓰여 있어서, 카드 1을 원래 값(12월,
이 달 제주 축제 1개)으로 되돌린 사본을 쓴다.
"""

import pytest

from agent import demo_cards
from agent.draft_contracts import IdeaProposal


def december_demo_proposal() -> IdeaProposal:
    """카드 1을 12월로 되돌린 데모 카드 묶음."""
    proposal = demo_cards.demo_proposal()
    first = proposal.ideas[0]
    first = first.model_copy(
        update={
            "timing": first.timing.model_copy(
                update={"recommended_months": [12], "jeju_festivals_in_month": 1}
            ),
            "hypotheses": [h.replace("1월", "12월", 1) for h in first.hypotheses],
        }
    )
    return proposal.model_copy(update={"ideas": [first, *proposal.ideas[1:]]})


@pytest.fixture
def december_demo(monkeypatch):
    """앱이 부르는 데모 카드도 12월 사본으로 바꾼다."""
    import agent.proposals

    monkeypatch.setattr(agent.proposals, "demo_proposal", december_demo_proposal)
