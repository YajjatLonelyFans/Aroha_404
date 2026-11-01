from fastapi import APIRouter, Query, Request

from app.schemas.health import HealthResponse
from app.services.health_service import check_health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    request: Request,
    deep: bool = Query(False, description="Also call Open-Meteo, Nominatim, the imagery provider, Gemini (model lookup) "
                                          "and Meko once each"),
) -> HealthResponse:
    state = request.app.state
    return await check_health(state.settings, state.mongo, state.assumptions, deep=deep, memory=state.memory,
                              tiles=state.tiles)
