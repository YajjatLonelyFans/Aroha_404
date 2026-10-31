"""Google Gemini adapter (REST, generateContent). Docs: https://ai.google.dev/api/generate-content

Free-tier keys are rate limited: HTTP 429 is reported at once (no retry) so the
caller can fall back to a template reply instead of burning quota.
"""

import logging
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.integrations.llm.base import LLMRateLimited, LLMReply, LLMUnavailable

log = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT_S = 30.0


class _ServerError(Exception):
    pass


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, (_ServerError, httpx.TimeoutException, httpx.TransportError))


class GeminiProvider:
    is_mock = False

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        *,
        base_url: str = GEMINI_URL,
        attempts: int = 2,
        backoff_s: float = 0.5,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self.model = model
        self._url = f"{base_url.rstrip('/')}/models/{model}:generateContent"
        self._attempts = attempts
        self._backoff_s = backoff_s

    async def generate(
        self, *, system: str, prompt: str, max_output_tokens: int = 700, temperature: float = 0.2
    ) -> LLMReply:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_output_tokens, "temperature": temperature},
        }
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._attempts),
            wait=wait_exponential(multiplier=self._backoff_s, max=4),
            retry=retry_if_exception(_retryable),
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    resp = await self._client.post(
                        self._url, json=body, headers={"x-goog-api-key": self._api_key}, timeout=TIMEOUT_S
                    )
                    if resp.status_code >= 500:
                        raise _ServerError(f"HTTP {resp.status_code}")
        except (_ServerError, httpx.HTTPError) as exc:
            log.warning("Gemini request failed: %s", exc)
            raise LLMUnavailable("The assistant is not responding right now.") from exc

        if resp.status_code == 429:
            raise LLMRateLimited()
        if resp.status_code >= 400:
            raise LLMUnavailable(f"The assistant rejected the request ({_error_message(resp)}).")
        return self._parse(resp.json())

    def _parse(self, data: dict[str, Any]) -> LLMReply:
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise LLMUnavailable(f"The assistant returned no reply ({reason}).")
        first = candidates[0]
        text = "".join(p.get("text", "") for p in (first.get("content") or {}).get("parts", [])).strip()
        if not text:
            raise LLMUnavailable(f"The assistant returned an empty reply ({first.get('finishReason')}).")
        usage = data.get("usageMetadata") or {}
        return LLMReply(
            text=text,
            model=data.get("modelVersion") or self.model,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
        )


def _error_message(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("error", {}).get("status") or f"HTTP {resp.status_code}")
    except ValueError:
        return f"HTTP {resp.status_code}"
