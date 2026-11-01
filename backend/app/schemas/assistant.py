from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.contracts import AgentOutput


class ChatRequest(BaseModel):
    user_id: str
    message: str = Field(min_length=1, max_length=2000)
    meko_enabled: bool = True


class MemoryCallOut(BaseModel):
    """One call to Meko, for the agent log: proof that memory is live."""

    tool: str
    latency_ms: int
    ok: bool
    error: str | None = None


class MemoryInfo(BaseModel):
    enabled: bool
    live: bool  # a real Meko call succeeded this turn
    is_mock: bool
    recalled: int
    shared: int = 0  # promoted lessons from the shared knowledge base
    written: int  # memories queued for saving after the reply
    error: str | None = None
    calls: list[MemoryCallOut] = Field(default_factory=list)  # recall-phase calls this turn


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
    latency_ms: int
    timings: dict[str, int]  # records_ms, recall_ms, agents_ms, compose_ms


class AgentLogMemory(BaseModel):
    enabled: bool
    live: bool
    is_mock: bool
    error: str | None
    calls: list[MemoryCallOut]
    commit_calls: list[MemoryCallOut] | None  # saved after the reply; null until the save has run


class AgentLogOut(BaseModel):
    run_id: str
    created_at: datetime
    agents: list[str]
    latency_ms: int
    timings: dict[str, int]
    memory: AgentLogMemory
    llm: LLMInfo
    is_mock: bool


class AgentLogsResponse(BaseModel):
    user_id: str
    logs: list[AgentLogOut]  # newest first
