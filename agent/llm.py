"""LLM 호출 인터페이스.

LLM 공급자는 아직 A, B가 합의 전이다 (CLAUDE.md 6절). Agent 코드는 이 인터페이스만 알고,
공급자가 정해지면 같은 모양의 어댑터 하나만 추가한다.
"""

from typing import Protocol


class LLMError(RuntimeError):
    """LLM 호출 실패. 메시지는 화면에 그대로 보여줘도 되는 문장이다 (키를 넣지 않는다)."""


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str) -> str:
        """system 지시와 user 내용을 보내고, JSON 문자열 응답을 그대로 돌려준다.

        응답이 계약에 맞는지는 호출하는 쪽이 코드로 검사한다.
        실패하면 LLMError를 던진다.
        """
        ...
