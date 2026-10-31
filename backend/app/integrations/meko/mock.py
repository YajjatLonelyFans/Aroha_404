"""In-process memory for development only (labelled mock; never used in the demo)."""

import itertools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from app.integrations.meko.base import MemoryCall, MemoryHit


class MockMemorySession:
    def __init__(self, store: "MockMemoryProvider") -> None:
        self._p = store
        self.calls: list[MemoryCall] = []

    async def ensure_conversation(self, user_id: str, existing: str | None) -> str:
        self.calls.append(MemoryCall("mock.conversation_create", 0, True))
        return existing or f"mock-conv-{user_id}"

    async def search(self, conversation_id: str, queries: dict[str, str], k: int = 5) -> list[MemoryHit]:
        self.calls.append(MemoryCall("mock.memory_search", 0, True))
        out: list[MemoryHit] = []
        for agent_id in queries:
            rows = [h for conv, h in self._p.rows if conv == conversation_id and h.agent_id == agent_id]
            out += list(reversed(rows))[:k]
        return out

    async def add(self, conversation_id: str, agent_id: str, text: str, metadata: dict[str, Any]) -> str | None:
        self.calls.append(MemoryCall("mock.memory_add", 0, True))
        memory_id = f"mock-mem-{next(self._p.ids)}"
        self._p.rows.append((conversation_id, MemoryHit(memory_id, text, agent_id, dict(metadata))))
        return memory_id

    async def shared_search(self, conversation_id: str, query: str, k: int = 3) -> list[MemoryHit]:
        self.calls.append(MemoryCall("mock.knowledgebase_search", 0, True))
        return list(self._p.shared[:k])

    async def promote(self, conversation_id: str, memory_ids: list[str], agent_id: str) -> None:
        self.calls.append(MemoryCall("mock.memory_promote", 0, True))
        moving = [h for _, h in self._p.rows if h.id in memory_ids]
        self._p.rows = [(c, h) for c, h in self._p.rows if h.id not in memory_ids]
        self._p.shared += moving


class MockMemoryProvider:
    is_mock = True

    def __init__(self) -> None:
        self.rows: list[tuple[str, MemoryHit]] = []
        self.shared: list[MemoryHit] = []
        self.ids = itertools.count(1)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[MockMemorySession]:
        yield MockMemorySession(self)
