"""Builds the `/api/health` report: liveness plus the state of each dependency.

Without `deep`, external services are only checked for configuration. With
`deep=true` (the pre-demo check) each one is called once: Open-Meteo, Nominatim's
status endpoint, one satellite tile, the Gemini model lookup (uses no generation
quota) and a Meko connection.
"""

import asyncio

import httpx
from pymongo import AsyncMongoClient

from app import __version__
from app.core.assumptions import Assumptions
from app.core.settings import Settings, is_configured
from app.db.client import ping
from app.integrations.llm.gemini import GEMINI_URL
from app.integrations.meko.base import MemoryProvider, MemoryUnavailable
from app.integrations.tiles.base import TileNotFound, TileProvider, TilesUnavailable
from app.integrations.tiles.factory import tile_source
from app.schemas.health import AssumptionsStatus, DependencyStatus, HealthResponse

PROBE_TIMEOUT_S = 10.0
MEKO_PROBE_TIMEOUT_S = 30.0
# A fixed point in central Delhi, used only to prove the forecast API answers.
_PROBE_PARAMS = {"latitude": 28.61, "longitude": 77.21, "current": "temperature_2m"}


async def _mongo_status(client: AsyncMongoClient | None) -> DependencyStatus:
    if client is None:
        return DependencyStatus(status="not_configured", detail="Set MONGODB_URI")
    error = await ping(client)
    if error:
        return DependencyStatus(status="error", detail=error)
    return DependencyStatus(status="ok")


async def _http_probe(url: str, **kwargs) -> DependencyStatus:
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as http:
            resp = await http.get(url, **kwargs)
        if resp.status_code >= 400:
            return DependencyStatus(status="error", detail=f"HTTP {resp.status_code}")
        return DependencyStatus(status="ok")
    except httpx.HTTPError as exc:
        return DependencyStatus(status="error", detail=type(exc).__name__)


def _config_status(*values: str, hint: str, is_mock: bool) -> DependencyStatus:
    if is_mock:
        return DependencyStatus(status="configured", detail="Mock in use", is_mock=True)
    if all(is_configured(v) for v in values):
        return DependencyStatus(status="configured", detail="Add ?deep=true to check live")
    return DependencyStatus(status="not_configured", detail=hint)


async def _imagery_status(settings: Settings, tiles: TileProvider | None, deep: bool) -> DependencyStatus:
    source = tile_source(settings)
    if source is None and not settings.use_mock_tiles:
        return DependencyStatus(status="not_configured", detail="MAP_TILES_PROVIDER must be 'maptiler' or 'esri'")
    status = _config_status(source.api_key if source else "", is_mock=settings.use_mock_tiles,
                            hint=f"Set {source.key_env} for satellite imagery" if source else "")
    if not deep or status.status != "configured" or status.is_mock or tiles is None:
        return status
    try:
        # One zoom-1 tile through the same adapter the map uses (its own key and retry).
        await asyncio.wait_for(tiles.get_tile(1, 1, 0), PROBE_TIMEOUT_S * 2)
        return DependencyStatus(status="ok")
    except (TilesUnavailable, TileNotFound, TimeoutError) as exc:
        return DependencyStatus(status="error", detail=getattr(exc, "message", type(exc).__name__))


async def _nominatim_status(settings: Settings, deep: bool) -> DependencyStatus:
    status = _config_status(settings.nominatim_user_agent, hint="Set NOMINATIM_USER_AGENT (app name and contact email)",
                            is_mock=settings.use_mock_geocoding)
    if not deep or status.status != "configured" or status.is_mock:
        return status
    # Nominatim's own status endpoint: one light request, within its usage policy.
    return await _http_probe(settings.nominatim_base_url.rstrip("/") + "/status",
                             params={"format": "json"}, headers={"User-Agent": settings.nominatim_user_agent})


async def _open_meteo_status(settings: Settings, deep: bool) -> DependencyStatus:
    if settings.use_mock_weather:
        return DependencyStatus(status="configured", detail="Mock weather in use", is_mock=True)
    if not deep:
        return DependencyStatus(status="configured", detail="Add ?deep=true to check live")
    return await _http_probe(settings.open_meteo_forecast_url, params=_PROBE_PARAMS)


async def _llm_status(settings: Settings, deep: bool) -> DependencyStatus:
    status = _config_status(settings.llm_provider, settings.llm_api_key, settings.llm_model,
                            hint="Set LLM_PROVIDER, LLM_API_KEY and LLM_MODEL", is_mock=settings.use_mock_llm)
    if status.status == "configured" and not status.is_mock and settings.llm_provider.lower() != "gemini":
        # Matches main.py, which only builds a Gemini client; never send another provider's key to Google.
        return DependencyStatus(status="not_configured",
                                detail=f"LLM_PROVIDER '{settings.llm_provider}' is not supported; use 'gemini'")
    if not deep or status.status != "configured" or status.is_mock:
        return status
    # Looking up the model checks the key and model name without spending generation quota.
    return await _http_probe(f"{GEMINI_URL}/models/{settings.llm_model}",
                             headers={"x-goog-api-key": settings.llm_api_key})


async def _meko_status(settings: Settings, memory: MemoryProvider | None, deep: bool) -> DependencyStatus:
    status = _config_status(settings.meko_mcp_url, settings.meko_api_key,
                            hint="Set MEKO_API_KEY", is_mock=settings.use_mock_meko)
    if not deep or memory is None or memory.is_mock:
        return status
    try:
        async def probe() -> None:
            async with memory.session() as ms:
                await ms.datapack_id()
        await asyncio.wait_for(probe(), MEKO_PROBE_TIMEOUT_S)
        return DependencyStatus(status="ok")
    except (MemoryUnavailable, TimeoutError) as exc:
        return DependencyStatus(status="error", detail=getattr(exc, "message", type(exc).__name__))


async def check_health(
    settings: Settings,
    mongo: AsyncMongoClient | None,
    assumptions: Assumptions,
    deep: bool = False,
    memory: MemoryProvider | None = None,
    tiles: TileProvider | None = None,
) -> HealthResponse:
    mongo_s, meteo_s, llm_s, meko_s, nominatim_s, imagery_s = await asyncio.gather(
        _mongo_status(mongo),
        _open_meteo_status(settings, deep),
        _llm_status(settings, deep),
        _meko_status(settings, memory, deep),
        _nominatim_status(settings, deep),
        _imagery_status(settings, tiles, deep),
    )
    dependencies = {
        "mongo": mongo_s,
        "open_meteo": meteo_s,
        "nominatim": nominatim_s,
        "satellite_imagery": imagery_s,
        "meko": meko_s,
        "llm": llm_s,
    }
    missing = assumptions.missing_fields()
    healthy = dependencies["mongo"].status == "ok" and not missing
    return HealthResponse(
        status="ok" if healthy else "degraded",
        version=__version__,
        app_env=settings.app_env,
        dependencies=dependencies,
        assumptions=AssumptionsStatus(version=assumptions.version, complete=not missing, missing=missing),
    )
