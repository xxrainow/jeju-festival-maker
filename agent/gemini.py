"""Gemini 어댑터 (LLMClient 구현). 새 의존성 없이 httpx로 Gemini Interactions API를 부른다.

문서 (2026-11 확인):
- Interactions API: https://ai.google.dev/gemini-api/docs/interactions
  (generateContent도 계속 지원되지만 새 개발에는 Interactions API를 권장)
- 모델: https://ai.google.dev/gemini-api/docs/models

키는 .env의 LLM_API_KEY로만 받고, 오류 문장·로그에 넣지 않는다 (CLAUDE.md 7절).
응답이 계약에 맞는지는 호출하는 쪽(idea_cards 등)이 코드로 검사한다.
"""

import httpx

from agent.llm import LLMError

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
API_REVISION = "2026-05-20"
DEFAULT_MODEL = "gemini-3.5-flash-lite"  # 무료 하루 요청이 Flash보다 넉넉함. .env의 LLM_MODEL로 바꾼다
MAX_OUTPUT_TOKENS = 4096

_STATUS_HINTS = {
    400: "요청 형식이 맞지 않아요. 모델 이름(LLM_MODEL)을 확인해주세요.",
    401: "API 키가 올바르지 않아요. .env의 LLM_API_KEY를 확인해주세요.",
    403: "API 키에 권한이 없어요. Google AI Studio에서 키와 프로젝트를 확인해주세요.",
    404: "모델을 찾지 못했어요. .env의 LLM_MODEL을 확인해주세요.",
    429: "무료 사용 한도를 넘었거나 요청이 너무 많아요. 잠시 뒤에 다시 시도해주세요.",
}


class GeminiClient:
    """agent.llm.LLMClient 모양을 따르는 Gemini 클라이언트."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        timeout: float = 30,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise LLMError("Gemini API 키가 없어요. .env의 LLM_API_KEY를 채워주세요.")
        self._key = api_key
        self.model = model or DEFAULT_MODEL
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def complete_json(self, system: str, user: str) -> str:
        body = {
            "model": self.model,
            "system_instruction": system,
            "input": user,
            "response_format": {"type": "text", "mime_type": "application/json"},
            "generation_config": {"thinking_level": "low", "max_output_tokens": MAX_OUTPUT_TOKENS},
        }
        headers = {
            "x-goog-api-key": self._key,
            "Api-Revision": API_REVISION,
            "Content-Type": "application/json",
        }
        try:
            res = self._client.post(ENDPOINT, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMError("AI 응답이 너무 오래 걸려요. 잠시 뒤에 다시 시도해주세요.") from exc
        except httpx.HTTPError as exc:
            raise LLMError("AI 서버에 연결하지 못했어요. 인터넷 연결을 확인해주세요.") from exc
        if res.status_code != 200:
            hint = _STATUS_HINTS.get(
                res.status_code, "AI 서버 오류예요. 잠시 뒤에 다시 시도해주세요."
            )
            raise LLMError(f"{hint} (HTTP {res.status_code})")
        try:
            return extract_text(res.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError("AI 응답을 읽지 못했어요.") from exc


def extract_text(data: dict) -> str:
    """Interactions 응답에서 모델이 쓴 text를 꺼낸다 (steps[type=model_output].content[type=text])."""
    if data.get("status") not in (None, "completed"):
        raise ValueError(f"응답 상태가 completed가 아니에요: {data.get('status')}")
    texts = [
        c["text"]
        for step in data.get("steps", [])
        if step.get("type") == "model_output"
        for c in step.get("content", [])
        if c.get("type") == "text" and c.get("text")
    ]
    if not texts:
        raise ValueError("응답에 text가 없어요")
    return "".join(texts)


def from_settings(settings) -> GeminiClient | None:
    """설정에 Gemini가 정해져 있고 키가 있으면 클라이언트를, 아니면 None을 준다."""
    provider = (settings.llm_provider or "").strip().lower()
    key = settings.llm_api_key.get_secret_value()
    if provider != "gemini" or not key:
        return None
    return GeminiClient(key, settings.llm_model, timeout=settings.request_timeout_seconds)
