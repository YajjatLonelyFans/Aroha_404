from pydantic import BaseModel

from app.schemas.common import Source

OSM_ATTRIBUTION = "© OpenStreetMap contributors"


class PlaceOut(BaseModel):
    display_name: str
    lat: float
    lon: float
    category: str | None
    type: str | None


class GeoSearchResponse(BaseModel):
    query: str
    results: list[PlaceOut]
    attribution: str = OSM_ATTRIBUTION
    sources: list[Source]
    cached: bool
    is_mock: bool
