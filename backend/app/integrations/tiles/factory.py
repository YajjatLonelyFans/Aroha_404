"""Picks the satellite tile provider from settings (MAP_TILES_PROVIDER)."""

import logging
from dataclasses import dataclass

import httpx

from app.core.settings import Settings, is_configured
from app.integrations.tiles.base import TileProvider, UnconfiguredTiles
from app.integrations.tiles.mock import MockTiles
from app.integrations.tiles.raster import RasterTiles

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TileSource:
    name: str
    key_env: str  # the .env variable that holds the key
    key_param: str  # query parameter the provider expects
    api_key: str
    url_template: str
    attribution: str


def tile_source(settings: Settings) -> TileSource | None:
    provider = settings.map_tiles_provider.strip().lower()
    if provider == "maptiler":
        return TileSource("MapTiler", "MAPTILER_API_KEY", "key", settings.maptiler_api_key,
                          settings.maptiler_tile_url, settings.maptiler_attribution)
    if provider == "esri":
        return TileSource("Esri", "ESRI_API_KEY", "token", settings.esri_api_key,
                          settings.esri_imagery_tile_url, settings.esri_imagery_attribution)
    return None


def build_tile_provider(settings: Settings, http: httpx.AsyncClient) -> TileProvider:
    if settings.use_mock_tiles:
        log.warning("USE_MOCK_TILES is on: the map shows grey mock tiles, labelled mock")
        return MockTiles()
    source = tile_source(settings)
    if source is None:
        reason = f"Satellite imagery is not set up (MAP_TILES_PROVIDER '{settings.map_tiles_provider}' is unknown)."
    elif not is_configured(source.api_key):
        reason = f"Satellite imagery is not set up ({source.key_env})."
    else:
        return RasterTiles(http, name=source.name, url_template=source.url_template, key_param=source.key_param,
                           api_key=source.api_key, attribution=source.attribution)
    log.warning("%s The map has no imagery; pins still work.", reason)
    return UnconfiguredTiles(reason)
