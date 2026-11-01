"""Recent chat turns for the agent log panel: agents used, timings, and every Meko call."""

from typing import Any

from app.db import collections as c
from app.db.store import DocumentStore
from app.schemas.assistant import AgentLogMemory, AgentLogOut, AgentLogsResponse, LLMInfo, MemoryCallOut


def _calls(rows: list[dict[str, Any]] | None) -> list[MemoryCallOut] | None:
    return None if rows is None else [MemoryCallOut(**r) for r in rows]


async def recent_logs(store: DocumentStore, user_id: str, limit: int) -> AgentLogsResponse:
    docs = await store.find(c.AGENT_LOGS, {"user_id": user_id})
    docs.sort(key=lambda d: d["created_at"], reverse=True)
    logs = []
    for d in docs[:limit]:
        meko = d.get("meko", {})
        logs.append(AgentLogOut(
            run_id=d["run_id"],
            created_at=d["created_at"],
            agents=d.get("agents", []),
            latency_ms=d.get("latency_ms", 0),
            timings=d.get("timings", {}),
            memory=AgentLogMemory(
                enabled=meko.get("enabled", False),
                live=meko.get("live", False),
                is_mock=meko.get("is_mock", False),
                error=meko.get("error"),
                calls=_calls(meko.get("calls")) or [],
                commit_calls=_calls(d.get("meko_commit_calls")),
            ),
            llm=LLMInfo(**d["llm"]),
            is_mock=d.get("is_mock", False),
        ))
    return AgentLogsResponse(user_id=user_id, logs=logs)
