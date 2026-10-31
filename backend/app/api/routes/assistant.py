from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends

from app.agents.orchestrator.pipeline import Orchestrator
from app.api.deps import get_orchestrator
from app.schemas.assistant import ChatRequest, ChatResponse

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    background: BackgroundTasks,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
) -> ChatResponse:
    """One chat turn. With meko_enabled the assistant recalls this homeowner; without it, it starts fresh.
    New memories are saved after the reply is sent."""
    response, commit = await orchestrator.chat(body)
    if commit is not None:
        background.add_task(commit)
    return response
