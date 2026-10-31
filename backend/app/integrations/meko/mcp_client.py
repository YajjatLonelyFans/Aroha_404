"""Meko over its hosted MCP server (tool reference: docs/MEKO_INTEGRATION.md).

Observed behaviour this client relies on (spike, 1 Nov 2026):
- results arrive as a JSON string in structuredContent["result"];
- tool errors can come back with isError=False as {"error": ...} or "Error ..." text;
- every tool needs a conversation_id, so a bootstrap conversation is used to find
  or create the datapack;
- searches take ~10 s each, but calls on one session can run in parallel.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from app.integrations.meko.base import MemoryCall, MemoryHit, MemoryUnavailable, agent_key

log = logging.getLogger(__name__)

CONNECT_TIMEOUT_S = 20.0
CALL_TIMEOUT_S = 30.0


def parse_result(result: Any) -> Any:
    """Unwrap a CallToolResult into Python data, raising MemoryUnavailable on any error shape."""
    d = result.model_dump(by_alias=True)
    raw = (d.get("structuredContent") or {}).get("result")
    if raw is None:
        raw = " ".join(c.get("text", "") for c in d.get("content", []) if c.get("type") == "text")
    if d.get("isError"):
        raise MemoryUnavailable(f"Memory service error: {str(raw)[:200]}")
    if isinstance(raw, str):
        if raw.lstrip().startswith("Error"):
            raise MemoryUnavailable(f"Memory service error: {raw[:200]}")
        try:
            raw = json.loads(raw)
        except ValueError:
            return raw
    if isinstance(raw, dict) and "error" in raw:
        raise MemoryUnavailable(f"Memory service error: {raw.get('error')}: {str(raw.get('detail', ''))[:200]}")
    return raw


class MekoSession:
    def __init__(self, session: Any, provider: "MekoMcpProvider") -> None:
        self._s = session
        self._p = provider
        self.calls: list[MemoryCall] = []

    async def _call(self, tool: str, args: dict[str, Any]) -> Any:
        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(self._s.call_tool(tool, args), CALL_TIMEOUT_S)
            data = parse_result(result)
        except MemoryUnavailable as exc:
            self.calls.append(MemoryCall(tool, _ms(start), False, exc.message))
            raise
        except Exception as exc:
            self.calls.append(MemoryCall(tool, _ms(start), False, type(exc).__name__))
            raise MemoryUnavailable(f"Memory service call {tool} failed.") from exc
        self.calls.append(MemoryCall(tool, _ms(start), True))
        return data

    async def datapack_id(self) -> str:
        if self._p.datapack_id:
            return self._p.datapack_id
        boot = await self._call("conversation_create", {
            "agent_id": agent_key("orchestrator"), "title": "Aroha datapack lookup", "session_id": "aroha-bootstrap",
        })
        found = await self._call("datapack_search", {"conversation_id": boot["id"], "name": self._p.datapack_name})
        packs = found.get("datapacks") or []
        if packs:
            self._p.datapack_id = packs[0]["datapack_id"]
        else:
            made = await self._call("datapack_create", {"name": self._p.datapack_name, "conversation_id": boot["id"]})
            self._p.datapack_id = made["datapack_id"]
            log.info("Created Meko datapack %s", self._p.datapack_name)
        return self._p.datapack_id

    async def ensure_conversation(self, user_id: str, existing: str | None) -> str:
        if existing:
            return existing
        conv = await self._call("conversation_create", {
            "agent_id": agent_key("orchestrator"),
            "title": "Aroha homeowner",
            "session_id": f"aroha-user-{user_id}",
            "datapack_id": await self.datapack_id(),
        })
        return conv["id"]

    async def search(self, conversation_id: str, queries: dict[str, str], k: int = 5) -> list[MemoryHit]:
        dp = await self.datapack_id()
        agent_ids = list(queries)
        results = await asyncio.gather(*[
            self._call("memory_search", {
                "query": query, "conversation_id": conversation_id, "run_id": conversation_id,
                "agent_id": agent_id, "limit": k, "datapack_id": dp,
            })
            for agent_id, query in queries.items()
        ])
        hits: dict[str, MemoryHit] = {}
        for agent_id, data in zip(agent_ids, results):
            for row in (data or {}).get("results", []):
                # Meko search does not filter by agent_id, so keep only this agent's rows.
                if row.get("agent_id") == agent_id and row["id"] not in hits:
                    hits[row["id"]] = MemoryHit(row["id"], row.get("memory", ""), row.get("agent_id"),
                                                row.get("metadata") or {}, row.get("score"))
        return sorted(hits.values(), key=lambda h: -(h.score or 0))

    async def add(self, conversation_id: str, agent_id: str, text: str, metadata: dict[str, Any]) -> str | None:
        data = await self._call("memory_add", {
            "text": text, "conversation_id": conversation_id, "agent_id": agent_id,
            "metadata": json.dumps(metadata), "datapack_id": await self.datapack_id(),
        })
        rows = (data or {}).get("results") or []
        return rows[0].get("id") if rows else None

    async def shared_search(self, conversation_id: str, query: str, k: int = 3) -> list[MemoryHit]:
        data = await self._call("knowledgebase_search", {
            "query": query, "conversation_id": conversation_id, "datapack_id": await self.datapack_id(), "limit": k,
        })
        hits = []
        for row in (data or {}).get("results", []):
            meta = row.get("metadata_filters") or {}
            hits.append(MemoryHit(row["id"], row.get("chunk_text", ""), meta.get("agent_id"), meta,
                                  row.get("rerank_score")))
        return hits

    async def promote(self, conversation_id: str, memory_ids: list[str], agent_id: str) -> None:
        await self._call("memory_promote", {
            "conversation_id": conversation_id, "memory_ids": memory_ids, "agent_id": agent_id,
            "datapack_id": await self.datapack_id(),
        })


def _ms(start: float) -> int:
    return round(1000 * (time.perf_counter() - start))


class MekoMcpProvider:
    is_mock = False

    def __init__(self, url: str, api_key: str, datapack_name: str) -> None:
        self._url = url
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self.datapack_name = datapack_name
        self.datapack_id: str | None = None  # found or created on first use, then cached

    @asynccontextmanager
    async def session(self) -> AsyncIterator[MekoSession]:
        stack = AsyncExitStack()
        try:
            http = await stack.enter_async_context(create_mcp_http_client(headers=self._headers))
            read, write = await stack.enter_async_context(streamable_http_client(self._url, http_client=http))
            client = await stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(client.initialize(), CONNECT_TIMEOUT_S)
        except Exception as exc:
            await _close(stack)
            log.warning("Could not connect to Meko: %s", exc)
            raise MemoryUnavailable("The memory service is not reachable.") from exc
        try:
            yield MekoSession(client, self)
        finally:
            await _close(stack)


async def _close(stack: AsyncExitStack) -> None:
    try:
        await stack.aclose()
    except Exception as exc:  # closing a half-open stream must not hide the real result
        log.debug("Ignoring error while closing the Meko session: %s", exc)
