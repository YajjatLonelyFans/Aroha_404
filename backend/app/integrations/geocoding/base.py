from dataclasses import dataclass
from typing import Protocol

from app.core.errors import AppError
from app.integrations.common import SourceInfo

Bbox = tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat


@dataclass(frozen=True)
class Place:
    display_name: str
    lat: float
    lon: float
    category: str | None
    type: str | None


@dataclass(frozen=True)
class GeocodeResult:
    places: list[Place]
    source: SourceInfo
    cached: bool = False


class GeocodingUnavailable(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("geocoding_unavailable", message, status_code=503, retryable=True)


class UnconfiguredGeocoder:
    """Stands in when NOMINATIM_USER_AGENT is not set: Nominatim requires an identifying agent."""

    is_mock = False

    async def search(self, query: str, bbox: Bbox, limit: int = 5) -> GeocodeResult:
        raise GeocodingUnavailable("Address search is not set up. Drop a pin on the map instead.")


class Geocoder(Protocol):
    is_mock: bool

    async def search(self, query: str, bbox: Bbox, limit: int = 5) -> GeocodeResult: ...
