"""Builds the `/api/health` report: liveness plus the state of each dependency."""

import httpx
from pymongo import AsyncMongoClient

from app import __version__
from app.core.assumptions import Assumptions
from app.core.settings import Settings, is_configured
from app.db.client import ping
from app.schemas.health import AssumptionsStatus, DependencyStatus, HealthResponse

OPEN_METEO_TIMEOUT_S = 5.0
# A fixed point in central Delhi, used only to prove the forecast API answers.
_PROBE_PARAMS = {"latitude": 28.61, "longitude": 77.21, "current": "temperature_2m"}


async def _mongo_status(client: AsyncMongoClient | None) -> DependencyStatus:
    if client is None:
        return DependencyStatus(status="not_configured", detail="Set MONGODB_URI")
    error = await ping(client)
    if error:
        return DependencyStatus(status="error", detail=error)
    return DependencyStatus(status="ok")


async def _open_meteo_status(settings: Settings, deep: bool) -> DependencyStatus:
    if settings.use_mock_weather:
        return DependencyStatus(status="configured", detail="Mock weather in use", is_mock=True)
    if not deep:
        return DependencyStatus(status="configured", detail="Add ?deep=true to check live")
    try:
        async with httpx.AsyncClient(timeout=OPEN_METEO_TIMEOUT_S) as http:
            resp = await http.get(settings.open_meteo_forecast_url, params=_PROBE_PARAMS)
        resp.raise_for_status()
        return DependencyStatus(status="ok")
    except httpx.HTTPError as exc:
        return DependencyStatus(status="error", detail=type(exc).__name__)


def _key_status(*values: str, hint: str, is_mock: bool) -> DependencyStatus:
    """Meko and the LLM are only checked for configuration until they are integrated."""
    if is_mock:
        return DependencyStatus(status="configured", detail="Mock in use", is_mock=True)
    if all(is_configured(v) for v in values):
        return DependencyStatus(status="configured")
    return DependencyStatus(status="not_configured", detail=hint)


async def check_health(
    settings: Settings,
    mongo: AsyncMongoClient | None,
    assumptions: Assumptions,
    deep: bool = False,
) -> HealthResponse:
    dependencies = {
        "mongo": await _mongo_status(mongo),
        "open_meteo": await _open_meteo_status(settings, deep),
        "nominatim": _key_status(
            settings.nominatim_user_agent,
            hint="Set NOMINATIM_USER_AGENT (app name and contact email)",
            is_mock=settings.use_mock_geocoding,
        ),
        "meko": _key_status(
            settings.meko_mcp_url,
            settings.meko_api_key,
            hint="Set MEKO_API_KEY",
            is_mock=settings.use_mock_meko,
        ),
        "llm": _key_status(
            settings.llm_provider,
            settings.llm_api_key,
            settings.llm_model,
            hint="Set LLM_PROVIDER, LLM_API_KEY and LLM_MODEL",
            is_mock=settings.use_mock_llm,
        ),
    }
    missing = assumptions.missing_fields()
    healthy = dependencies["mongo"].status == "ok" and not missing
    return HealthResponse(
        status="ok" if healthy else "degraded",
        version=__version__,
        app_env=settings.app_env,
        dependencies=dependencies,
        assumptions=AssumptionsStatus(
            version=assumptions.version, complete=not missing, missing=missing
        ),
    )
