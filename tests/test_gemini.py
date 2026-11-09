import json

import httpx
import pytest
from pydantic import SecretStr

from agent.gemini import (
    API_REVISION,
    DEFAULT_MODEL,
    ENDPOINT,
    GeminiClient,
    extract_text,
    from_settings,
)
from agent.llm import LLMError
from app.settings import Settings

KEY = "test-key-not-real"


def ok_response(text: str) -> dict:
    return {
        "id": "int_1",
        "status": "completed",
        "steps": [
            {"type": "user_input", "content": [{"type": "text", "text": "질문"}]},
            {
                "type": "model_output",
                "status": "completed",
                "content": [{"type": "text", "text": text}],
            },
        ],
    }


def client_with(handler) -> GeminiClient:
    return GeminiClient(KEY, transport=httpx.MockTransport(handler))


def test_request_shape_and_text_extraction():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_response('{"picks": []}'))

    out = client_with(handler).complete_json("시스템 지시", "사용자 입력")
    assert out == '{"picks": []}'
    assert seen["url"] == ENDPOINT
    assert seen["headers"]["x-goog-api-key"] == KEY
    assert seen["headers"]["Api-Revision"] == API_REVISION
    body = seen["body"]
    assert body["model"] == DEFAULT_MODEL
    assert body["system_instruction"] == "시스템 지시"
    assert body["input"] == "사용자 입력"
    assert body["response_format"]["mime_type"] == "application/json"


def test_extract_text_joins_model_output_only():
    data = ok_response("앞")
    data["steps"][1]["content"].append({"type": "text", "text": "뒤"})
    assert extract_text(data) == "앞뒤"
    with pytest.raises(ValueError):
        extract_text({"status": "completed", "steps": [{"type": "user_input", "content": []}]})
    with pytest.raises(ValueError):
        extract_text({"status": "failed", "steps": []})


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "API 키가 올바르지"), (404, "LLM_MODEL"), (429, "한도"), (500, "서버 오류")],
)
def test_http_errors_become_friendly_llm_errors(status, message):
    client = client_with(lambda request: httpx.Response(status, json={"error": {"message": KEY}}))
    with pytest.raises(LLMError, match=message) as info:
        client.complete_json("s", "u")
    assert KEY not in str(info.value)  # 키나 서버 원문을 화면 문장에 넣지 않는다


def test_timeout_and_connection_errors():
    def timeout(request):
        raise httpx.ReadTimeout("느림", request=request)

    with pytest.raises(LLMError, match="오래 걸려요"):
        client_with(timeout).complete_json("s", "u")

    def offline(request):
        raise httpx.ConnectError("끊김", request=request)

    with pytest.raises(LLMError, match="인터넷"):
        client_with(offline).complete_json("s", "u")


def test_unreadable_response():
    client = client_with(lambda request: httpx.Response(200, text="not json"))
    with pytest.raises(LLMError, match="읽지 못했어요"):
        client.complete_json("s", "u")


def test_missing_key_is_rejected():
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        GeminiClient("")


def test_from_settings():
    base = {"_env_file": None}
    assert from_settings(Settings(**base)) is None
    assert from_settings(Settings(**base, llm_provider="gemini")) is None  # 키 없음
    assert (
        from_settings(Settings(**base, llm_provider="openai", llm_api_key=SecretStr(KEY))) is None
    )
    client = from_settings(Settings(**base, llm_provider="Gemini", llm_api_key=SecretStr(KEY)))
    assert client.model == DEFAULT_MODEL
    client = from_settings(
        Settings(
            **base, llm_provider="gemini", llm_model="gemini-3.8-flash", llm_api_key=SecretStr(KEY)
        )
    )
    assert client.model == "gemini-3.8-flash"
