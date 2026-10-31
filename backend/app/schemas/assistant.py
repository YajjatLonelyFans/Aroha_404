from typing import Literal

from pydantic import BaseModel, Field

from app.agents.contracts import AgentOutput


class ChatRequest(BaseModel):
    user_id: str
    message: str = Field(min_length=1, max_length=2000)
    meko_enabled: bool = True


class MemoryInfo(BaseModel):
    enabled: bool
    live: bool  # a real Meko call succeeded this turn
    is_mock: bool
    recalled: int
    written: int  # memories queued for saving after the reply
    error: str | None = None


class LLMInfo(BaseModel):
    used: bool
    model: str | None
    is_mock: bool
    fallback_reason: Literal["not_configured", "rate_limited", "unavailable", "invalid_numbers", "no_facts"] | None


class ChatResponse(BaseModel):
    run_id: str
    reply: str
    agents: list[str]
    agent_outputs: list[AgentOutput]
    memory: MemoryInfo
    llm: LLMInfo
    notes: list[str]
