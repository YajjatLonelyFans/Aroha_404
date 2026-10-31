"""Agent input and output envelopes (docs/AGENT_CONTRACTS.md)."""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.integrations.meko.base import MemoryHit
from app.schemas.common import Confidence, Source

AgentName = Literal["roof", "weather", "financial", "policy", "application"]


class MemoryCandidate(BaseModel):
    """A summary an agent proposes to remember. Only the orchestrator commits it."""

    agent: AgentName
    text: str  # no addresses, coordinates, consumer numbers or names
    record_id: str | None = None  # the MongoDB record it summarises; used to avoid duplicates
    promote_to_shared: bool = False
    verified: bool = False


class AgentOutput(BaseModel):
    agent: AgentName
    status: Literal["ok", "partial", "error"]
    result: dict[str, Any] = Field(default_factory=dict)
    facts: list[str] = Field(default_factory=list)  # plain statements with numbers already formatted
    assumptions: list[str] = Field(default_factory=list)
    confidence: Confidence | None = None
    sources: list[Source] = Field(default_factory=list)
    memory_writes: list[MemoryCandidate] = Field(default_factory=list)
    is_mock: bool = False
    error: str | None = None


@dataclass
class AgentContext:
    """What the orchestrator hands each agent for one chat turn."""

    user_id: str
    message: str
    user: dict[str, Any]
    property: dict[str, Any] | None = None
    assessment: dict[str, Any] | None = None
    estimate: dict[str, Any] | None = None
    recalled: list[MemoryHit] = field(default_factory=list)
    wants_forecast: bool = False


def inr(value: float | None) -> str:
    return "not available" if value is None else f"₹{value:,.0f}"


def num(value: float | None, digits: int = 0) -> str:
    return "not available" if value is None else f"{value:,.{digits}f}"
