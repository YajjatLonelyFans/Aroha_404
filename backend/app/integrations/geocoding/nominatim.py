"""Nominatim (OpenStreetMap) address search.

Usage policy (https://operations.osmfoundation.org/policies/nominatim/): an
identifying User-Agent, at most 1 request per second, no bulk use, results
cached, and "© OpenStreetMap contributors" shown wherever results appear.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import httpx

from app.integrations.common import SourceInfo
from app.integrations.geocoding.base import Bbox, GeocodeResult, GeocodingUnavailable, Place

log = logging.getLogger(__name__)

TIMEOUT_S = 10.0
SOURCE_NAME = "Nominatim (OpenStreetMap)"


class NominatimGeocoder:
    is_mock = False

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        user_agent: str,
        *,
        min_interval_s: float = 1.0,
        cache_ttl_s: float = 24 * 3600,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._url = base_url.rstrip("/") + "/search"
        self._user_agent = user_agent
        self._min_interval_s = min_interval_s
        self._cache_ttl_s = cache_ttl_s
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last_request: float | None = None
        self._cache: dict[tuple, tuple[float, GeocodeResult]] = {}

    async def search(self, query: str, bbox: Bbox, limit: int = 5) -> GeocodeResult:
        key = (" ".join(query.lower().split()), bbox, limit)
        hit = self._cache.get(key)
        if hit and self._clock() - hit[0] < self._cache_ttl_s:
            return GeocodeResult(hit[1].places, hit[1].source, cached=True)

        min_lon, min_lat, max_lon, max_lat = bbox
        params = {
            "q": query, "format": "jsonv2", "countrycodes": "in", "limit": limit,
            "viewbox": f"{min_lon},{max_lat},{max_lon},{min_lat}", "bounded": 1,
        }
        async with self._lock:  # one request at a time, spaced by min_interval_s
            if self._last_request is not None:
                wait = self._min_interval_s - (self._clock() - self._last_request)
                if wait > 0:
                    await self._sleep(wait)
            try:
                resp = await self._client.get(
                    self._url, params=params, headers={"User-Agent": self._user_agent}, timeout=TIMEOUT_S
                )
            except httpx.HTTPError as exc:
                log.warning("Nominatim request failed: %s", exc)
                raise GeocodingUnavailable("Address search is not responding. Drop a pin on the map instead.") from exc
            finally:
                self._last_request = self._clock()

        if resp.status_code == 429:
            raise GeocodingUnavailable("Address search is busy. Wait a moment or drop a pin on the map.")
        if resp.status_code >= 400:
            raise GeocodingUnavailable(f"Address search failed (HTTP {resp.status_code}). Drop a pin on the map.")
        try:
            rows = resp.json()
            places = [
                Place(r["display_name"], float(r["lat"]), float(r["lon"]), r.get("category"), r.get("type"))
                for r in rows
            ]
        except (ValueError, KeyError, TypeError) as exc:
            raise GeocodingUnavailable("Address search sent an unreadable response.") from exc

        result = GeocodeResult(places, SourceInfo(SOURCE_NAME, self._url, datetime.now(timezone.utc)))
        self._cache[key] = (self._clock(), result)
        return result
