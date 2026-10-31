"""Address search, limited to Delhi."""

from app.core.assumptions import Assumptions
from app.integrations.geocoding.base import Geocoder
from app.schemas.common import Source
from app.schemas.geo import OSM_ATTRIBUTION, GeoSearchResponse, PlaceOut

RESULT_LIMIT = 5


class GeoService:
    def __init__(self, geocoder: Geocoder, assumptions: Assumptions) -> None:
        self._geocoder = geocoder
        self._a = assumptions

    async def search(self, query: str) -> GeoSearchResponse:
        bbox = self._a.validation.delhi_bbox
        result = await self._geocoder.search(query.strip(), bbox, RESULT_LIMIT)
        min_lon, min_lat, max_lon, max_lat = bbox
        places = [
            PlaceOut(display_name=p.display_name, lat=p.lat, lon=p.lon, category=p.category, type=p.type)
            for p in result.places
            if min_lat <= p.lat <= max_lat and min_lon <= p.lon <= max_lon
        ]
        src = result.source
        return GeoSearchResponse(
            query=query,
            results=places,
            sources=[Source(name=src.name, url=src.url, retrieved_at=src.retrieved_at, note=OSM_ATTRIBUTION)],
            cached=result.cached,
            is_mock=src.is_mock,
        )
