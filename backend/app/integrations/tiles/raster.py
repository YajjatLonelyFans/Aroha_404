"""Satellite raster tiles from a keyed XYZ tile service, fetched server-side.

Providers (chosen by MAP_TILES_PROVIDER, see factory.py):
- MapTiler (default): https://docs.maptiler.com/cloud/api/maps/
  `https://api.maptiler.com/maps/{mapId}/256/{z}/{x}/{y}.jpg?key=…`. Free plan: no card,
  service pauses at the monthly limit, non-commercial use. Credit: © MapTiler © OpenStreetMap contributors.
- Esri World Imagery: https://developers.arcgis.com/maplibre-gl-js/maps/display-multiple-basemap-layers
  `…/World_Imagery/MapServer/tile/{z}/{y}/{x}?token=…` (row before column).

Tiles are not stored server-side; browsers may cache them. The credit line must be shown on the map.
"""

import logging

import httpx

from app.integrations.tiles.base import Tile, TileNotFound, TilesUnavailable

log = logging.getLogger(__name__)

TIMEOUT_S = 8.0
ATTEMPTS = 2


class RasterTiles:
    is_mock = False

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        name: str,
        url_template: str,
        key_param: str,
        api_key: str,
        attribution: str,
        max_zoom: int = 19,
    ) -> None:
        self._client = client
        self.name = name  # for logs, e.g. "MapTiler"
        self._template = url_template  # with {z}, {x}, {y} in the provider's order
        self._key_param = key_param
        self._key = api_key
        self.attribution = attribution
        self.max_zoom = max_zoom

    async def get_tile(self, z: int, x: int, y: int) -> Tile:
        url = self._template.format(z=z, x=x, y=y)
        for attempt in range(ATTEMPTS):
            try:
                resp = await self._client.get(url, params={self._key_param: self._key}, timeout=TIMEOUT_S)
                break
            except httpx.TransportError as exc:
                # One retry: the first tiles after a quiet spell have timed out once (MapTiler, live test).
                log.warning("%s tile request failed (attempt %d): %s", self.name, attempt + 1, type(exc).__name__)
                if attempt == ATTEMPTS - 1:
                    raise TilesUnavailable("Satellite imagery is not responding.") from exc
        if resp.status_code == 404:
            raise TileNotFound()
        if resp.status_code in (401, 403):
            # Never log the URL: it carries the key.
            log.error("%s rejected the tile request (HTTP %d): check the API key", self.name, resp.status_code)
            raise TilesUnavailable("Satellite imagery rejected our key.")
        if resp.status_code == 429:
            raise TilesUnavailable("Satellite imagery is over its free limit for now.")
        if resp.status_code >= 400:
            raise TilesUnavailable(f"Satellite imagery failed (HTTP {resp.status_code}).")
        media_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
        if not media_type.startswith("image/"):
            # Some services (ArcGIS) report errors such as a bad key as a 200 with a JSON body.
            log.error("%s sent %s instead of an image: check the API key", self.name, media_type)
            raise TilesUnavailable("Satellite imagery sent an unexpected response.")
        return Tile(resp.content, media_type)
