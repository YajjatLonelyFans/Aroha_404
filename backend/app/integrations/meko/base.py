"""Memory interface (Meko). MongoDB stays the system of record; this holds what agents recall.

Per-user scoping uses one Meko conversation per user: memories are tagged with
that conversation and searched by it. Per-agent scoping uses `agent_id`
("aroha:roof", ...), enforced on our side because Meko search does not filter by it.
"""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.errors import AppError


def agent_key(agent: str) -> str:
    return f"aroha:{agent}"


@dataclass(frozen=True)
class MemoryHit:
    id: str
    text: str
    agent_id: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None


@dataclass(frozen=True)
class MemoryCall:
    """One call to the memory service, kept for the agent log."""

    tool: str
    latency_ms: int
    ok: bool
    error: str | None = None


class MemoryUnavailable(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("memory_unavailable", message, status_code=503, retryable=True)


class MemorySession(Protocol):
    calls: list[MemoryCall]

    async def ensure_conversation(self, user_id: str, existing: str | None) -> str: ...

    async def search(self, conversation_id: str, queries: dict[str, str], k: int = 5) -> list[MemoryHit]:
        """One search per agent id ({agent_id: query}); only that agent's memories are kept."""
        ...

    async def add(
        self, conversation_id: str, agent_id: str, text: str, metadata: dict[str, Any]
    ) -> str | None: ...

    async def shared_search(self, conversation_id: str, query: str, k: int = 3) -> list[MemoryHit]:
        """Promoted, de-identified lessons in the datapack's shared knowledge base (any user can read)."""
        ...

    async def promote(self, conversation_id: str, memory_ids: list[str], agent_id: str) -> None:
        """Move memories into the shared knowledge base. One-way."""
        ...


class MemoryProvider(Protocol):
    is_mock: bool

    def session(self) -> AbstractAsyncContextManager[MemorySession]: ...
