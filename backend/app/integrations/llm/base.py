"""LLM interface. The LLM writes replies from facts it is given; it never computes numbers."""

from dataclasses import dataclass
from typing import Protocol

from app.core.errors import AppError


@dataclass(frozen=True)
class LLMReply:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    is_mock: bool = False


class LLMUnavailable(AppError):
    def __init__(self, message: str, code: str = "llm_unavailable") -> None:
        super().__init__(code, message, status_code=503, retryable=True)


class LLMRateLimited(LLMUnavailable):
    """Free-tier quota reached; callers fall back to a template reply."""

    def __init__(self, message: str = "The assistant's free quota is used up for now.") -> None:
        super().__init__(message, code="llm_rate_limited")


class LLMProvider(Protocol):
    is_mock: bool
    model: str

    async def generate(
        self, *, system: str, prompt: str, max_output_tokens: int = 700, temperature: float = 0.2
    ) -> LLMReply: ...
