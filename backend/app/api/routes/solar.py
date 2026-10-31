from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_solar_service
from app.schemas.solar import SolarEstimateRequest, SolarEstimateResponse
from app.services.solar_service import SolarService

router = APIRouter(prefix="/solar", tags=["solar"])


@router.post("/estimate", response_model=SolarEstimateResponse, status_code=201)
async def estimate(
    body: SolarEstimateRequest, svc: Annotated[SolarService, Depends(get_solar_service)]
) -> SolarEstimateResponse:
    """Monthly and yearly generation range with cost, savings and payback for 1-3 sizes."""
    return await svc.estimate(body)
