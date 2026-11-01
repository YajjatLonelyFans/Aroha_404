"""App factory: settings, logging, CORS, error handlers, routers and startup tasks."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError

from app import __version__
from app.api.routes import applications, assistant, geo, health, map, policy, roof, solar, users, weather
from app.core.assumptions import load_assumptions
from app.core.errors import UnexpectedErrorMiddleware, register_error_handlers
from app.core.logging import setup_logging
from app.core.ratelimit import ChatLimiter
from app.core.settings import Settings, get_settings, is_configured
from app.db.client import create_client
from app.db.indexes import ensure_indexes
from app.db.seed import load_policy_records, load_procedures, seed_database
from app.integrations.geocoding.base import UnconfiguredGeocoder
from app.integrations.geocoding.mock import MockGeocoder
from app.integrations.geocoding.nominatim import NominatimGeocoder
from app.integrations.llm.gemini import GeminiProvider
from app.integrations.llm.mock import MockLLM
from app.integrations.meko.mcp_client import MekoMcpProvider
from app.integrations.meko.mock import MockMemoryProvider
from app.integrations.tiles.factory import build_tile_provider
from app.integrations.weather.mock import MockWeatherProvider
from app.integrations.weather.open_meteo import OpenMeteoProvider

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        # A malformed assumptions file stops startup; null values only produce a warning.
        app.state.assumptions = load_assumptions()
        missing = app.state.assumptions.missing_fields()
        if missing:
            log.warning("assumptions.v1.json has %d unset value(s): %s", len(missing), missing)

        # A malformed seed file stops startup, like the assumptions file.
        load_policy_records()
        load_procedures()

        app.state.mongo = create_client(settings)
        if app.state.mongo is not None:
            try:
                await ensure_indexes(app.state.mongo[settings.mongodb_db])
                await seed_database(app.state.mongo[settings.mongodb_db])
            except PyMongoError as exc:
                # Keep serving so /api/health can report the problem.
                log.error("Could not prepare MongoDB (indexes, seed records): %s", exc)

        app.state.http = httpx.AsyncClient()
        if settings.use_mock_weather:
            log.warning("USE_MOCK_WEATHER is on: weather responses are recorded data, labelled mock")
            app.state.weather_provider = MockWeatherProvider()
        else:
            app.state.weather_provider = OpenMeteoProvider(
                app.state.http, settings.open_meteo_archive_url, settings.open_meteo_forecast_url
            )
        if settings.use_mock_geocoding:
            log.warning("USE_MOCK_GEOCODING is on: address search returns recorded data, labelled mock")
            app.state.geocoder = MockGeocoder()
        elif is_configured(settings.nominatim_user_agent):
            app.state.geocoder = NominatimGeocoder(
                app.state.http, settings.nominatim_base_url, settings.nominatim_user_agent
            )
        else:
            log.warning("NOMINATIM_USER_AGENT is not set; address search is off (pins still work)")
            app.state.geocoder = UnconfiguredGeocoder()

        app.state.tiles = build_tile_provider(settings, app.state.http)

        app.state.llm = None
        if settings.use_mock_llm:
            log.warning("USE_MOCK_LLM is on: chat replies come from a labelled mock")
            app.state.llm = MockLLM()
        elif settings.llm_provider.lower() == "gemini" and all(
            is_configured(v) for v in (settings.llm_api_key, settings.llm_model)
        ):
            app.state.llm = GeminiProvider(app.state.http, settings.llm_api_key, settings.llm_model)
        else:
            log.warning("No usable LLM configured; chat uses template replies")

        app.state.memory = None
        if settings.use_mock_meko:
            log.warning("USE_MOCK_MEKO is on: memory is in-process and labelled mock (never for the demo)")
            app.state.memory = MockMemoryProvider()
        elif is_configured(settings.meko_api_key):
            app.state.memory = MekoMcpProvider(settings.meko_mcp_url, settings.meko_api_key, settings.meko_datapack)
        else:
            log.warning("MEKO_API_KEY is not set; chat memory is off")

        app.state.chat_limiter = ChatLimiter(settings.chat_max_per_minute, settings.chat_max_total_per_minute)
        warm = None
        if isinstance(app.state.memory, MekoMcpProvider):
            # Finding the datapack takes ~8 s; do it now so the first chat does not pay for it.
            warm = asyncio.create_task(_warm_meko(app.state.memory))
        try:
            yield
        finally:
            if warm is not None and not warm.done():
                warm.cancel()
            await app.state.http.aclose()
            if app.state.mongo is not None:
                await app.state.mongo.close()

    app = FastAPI(title="Aroha API", version=__version__, lifespan=lifespan)
    # The last one added is the outermost: Timing → CORS → UnexpectedError → routes.
    # UnexpectedError sits inside CORS so even a 500 carries CORS headers.
    app.add_middleware(UnexpectedErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TimingMiddleware)
    register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    for module in (users, geo, map, roof, weather, solar, policy, applications, assistant):
        app.include_router(module.router, prefix="/api")
    return app


class TimingMiddleware:
    """Adds X-Response-Time-ms and logs API timings.

    Plain ASGI on purpose: Starlette's @app.middleware("http") makes the client wait
    for background tasks, which would hold every chat reply until memories are saved.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()

        async def send_with_timing(message: Message) -> None:
            if message["type"] == "http.response.start":
                ms = round(1000 * (time.perf_counter() - start))
                message.setdefault("headers", []).append((b"x-response-time-ms", str(ms).encode()))
                path = scope["path"]
                # A map view loads dozens of tiles; log only the ones that fail.
                if path.startswith("/api") and (not path.startswith("/api/tiles/") or message["status"] >= 400):
                    log.info("%s %s -> %d in %d ms", scope["method"], path, message["status"], ms)
            await send(message)

        await self.app(scope, receive, send_with_timing)


async def _warm_meko(memory: MekoMcpProvider) -> None:
    try:
        async with memory.session() as ms:
            await ms.datapack_id()
        log.info("Meko warmed: datapack %s ready", memory.datapack_name)
    except Exception as exc:  # warming is best effort; chat reports real failures itself
        log.warning("Could not warm Meko at startup: %s", exc)


app = create_app()
