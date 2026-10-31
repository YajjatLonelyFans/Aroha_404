"""App factory: settings, logging, CORS, error handlers, routers and startup tasks."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError

from app import __version__
from app.api.routes import health
from app.core.assumptions import load_assumptions
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.core.settings import Settings, get_settings
from app.db.client import create_client
from app.db.indexes import ensure_indexes

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

        app.state.mongo = create_client(settings)
        if app.state.mongo is not None:
            try:
                await ensure_indexes(app.state.mongo[settings.mongodb_db])
            except PyMongoError as exc:
                # Keep serving so /api/health can report the problem.
                log.error("Could not create MongoDB indexes: %s", exc)
        try:
            yield
        finally:
            if app.state.mongo is not None:
                await app.state.mongo.close()

    app = FastAPI(title="Aroha API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()
