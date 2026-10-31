from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_geo_service
from app.schemas.geo import GeoSearchResponse
from app.services.geo_service import GeoService

router = APIRouter(prefix="/geo", tags=["geo"])


@router.get("/search", response_model=GeoSearchResponse)
async def search(
    svc: Annotated[GeoService, Depends(get_geo_service)],
    q: Annotated[str, Query(min_length=3, max_length=200, description="Address or place in Delhi")],
) -> GeoSearchResponse:
    """Address search within Delhi. Call on Enter or after a pause, not on every keystroke."""
    return await svc.search(q)
