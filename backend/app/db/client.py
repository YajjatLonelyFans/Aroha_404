"""MongoDB client lifecycle, using PyMongo's async API."""

import logging
from datetime import timezone

from fastapi import Request
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.core.errors import AppError
from app.core.settings import Settings, is_configured

log = logging.getLogger(__name__)


def create_client(settings: Settings) -> AsyncMongoClient | None:
    """Build a client, or return None when MONGODB_URI is not set. Does not connect yet."""
    if not is_configured(settings.mongodb_uri):
        log.warning("MONGODB_URI is not set; database features are unavailable")
        return None
    return AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=settings.mongodb_timeout_ms,
        tz_aware=True,
        tzinfo=timezone.utc,
        appname="aroha-backend",
    )


async def ping(client: AsyncMongoClient) -> str | None:
    """Return None if the server answers, else a short error message."""
    try:
        await client.admin.command("ping")
        return None
    except PyMongoError as exc:
        log.warning("MongoDB ping failed: %s", exc)
        return type(exc).__name__


def get_db(request: Request) -> AsyncDatabase:
    """FastAPI dependency: the app database, or a 503 if MongoDB is not configured."""
    client: AsyncMongoClient | None = request.app.state.mongo
    if client is None:
        raise AppError(
            "database_unavailable",
            "The database is not configured.",
            status_code=503,
            retryable=True,
        )
    return client[request.app.state.settings.mongodb_db]
