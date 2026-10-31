from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_roof_service
from app.schemas.roof import RoofAssessRequest, RoofAssessResponse
from app.services.roof_service import RoofService

router = APIRouter(prefix="/roof", tags=["roof"])


@router.post("/assess", response_model=RoofAssessResponse, status_code=201)
async def assess(body: RoofAssessRequest, svc: Annotated[RoofService, Depends(get_roof_service)]) -> RoofAssessResponse:
    """Outline, no-go areas and shading → usable area, panel layout and capacity range."""
    return await svc.assess(body)
