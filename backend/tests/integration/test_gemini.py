import httpx
import pytest
import respx

from app.integrations.llm.base import LLMRateLimited, LLMUnavailable
from app.integrations.llm.gemini import GeminiProvider
from app.integrations.llm.mock import MockLLM

URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"
OK = {"candidates": [{"content": {"parts": [{"text": "About 3,899 kWh a year."}]}, "finishReason": "STOP"}],
      "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 9}, "modelVersion": "gemini-3.5-flash-lite"}


@pytest.fixture
async def llm():
    async with httpx.AsyncClient() as client:
        yield GeminiProvider(client, "test-key", "gemini-3.5-flash-lite", backoff_s=0)


@respx.mock
async def test_request_shape_and_parse(llm):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=OK))
    reply = await llm.generate(system="Be brief.", prompt="Question", max_output_tokens=50, temperature=0.1)
    req = route.calls.last.request
    assert req.headers["x-goog-api-key"] == "test-key"
    assert "key=" not in str(req.url)  # the key never goes in the URL
    body = __import__("json").loads(req.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "Be brief."
    assert body["contents"][0]["parts"][0]["text"] == "Question"
    assert body["generationConfig"] == {"maxOutputTokens": 50, "temperature": 0.1}
    assert reply.text == "About 3,899 kWh a year." and reply.output_tokens == 9 and not reply.is_mock


@respx.mock
async def test_rate_limit_is_not_retried(llm):
    route = respx.post(URL).mock(return_value=httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}}))
    with pytest.raises(LLMRateLimited):
        await llm.generate(system="s", prompt="p")
    assert route.call_count == 1


@respx.mock
async def test_server_error_is_retried_once(llm):
    route = respx.post(URL).mock(side_effect=[httpx.Response(503), httpx.Response(200, json=OK)])
    assert (await llm.generate(system="s", prompt="p")).text
    assert route.call_count == 2


@respx.mock
async def test_bad_request_reports_status_without_key(llm):
    respx.post(URL).mock(return_value=httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT"}}))
    with pytest.raises(LLMUnavailable) as exc:
        await llm.generate(system="s", prompt="p")
    assert "INVALID_ARGUMENT" in exc.value.message and "test-key" not in exc.value.message


@respx.mock
async def test_blocked_or_empty_reply_is_unavailable(llm):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(LLMUnavailable):
        await llm.generate(system="s", prompt="p")


async def test_mock_llm_only_repeats_facts():
    reply = await MockLLM().generate(system="s", prompt="Q\nFACTS (x):\n- Fact one 5.\n- Fact two.\n")
    assert reply.is_mock and "Mock" in reply.text and "Fact one 5." in reply.text
