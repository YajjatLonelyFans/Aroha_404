from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.agents.orchestrator.pipeline import Orchestrator
from app.api.deps import StoreDep, get_orchestrator
from app.core.errors import NotFoundError
from app.db import collections as c
from app.schemas.assistant import AgentLogsResponse, ChatRequest, ChatResponse
from app.services.agent_log_service import recent_logs

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    background: BackgroundTasks,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
) -> ChatResponse:
    """One chat turn. With meko_enabled the assistant recalls this homeowner; without it, it starts fresh.
    New memories are saved after the reply is sent. Limited per user per minute to protect the LLM quota."""
    response, commit = await orchestrator.chat(body)
    if commit is not None:
        background.add_task(commit)
    return response


@router.get("/logs", response_model=AgentLogsResponse)
async def logs(
    store: StoreDep,
    user_id: Annotated[str, Query()],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> AgentLogsResponse:
    """Recent chat turns for the agent log: agents, timings, and each Meko call, including the
    memory saves made after the reply."""
    if await store.get(c.USERS, user_id) is None:
        raise NotFoundError("User")
    return await recent_logs(store, user_id, limit)
