"""Weather cache storage. Documents follow docs/DATABASE_SCHEMA.md."""

from datetime import datetime
from typing import Any, Protocol

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c


class WeatherRepo(Protocol):
    async def find_climatology(self, key: dict[str, Any]) -> dict[str, Any] | None: ...
    async def save_climatology(self, key: dict[str, Any], doc: dict[str, Any]) -> str: ...
    async def find_current(self, key: dict[str, Any], now: datetime) -> dict[str, Any] | None: ...
    async def save_current(self, key: dict[str, Any], doc: dict[str, Any]) -> None: ...
    async def find_forecast(self, key: dict[str, Any], now: datetime) -> dict[str, Any] | None: ...
    async def save_forecast(self, key: dict[str, Any], doc: dict[str, Any]) -> None: ...


class MongoWeatherRepo:
    def __init__(self, db: AsyncDatabase) -> None:
        self._records = db[c.WEATHER_RECORDS]
        self._forecasts = db[c.WEATHER_FORECASTS]

    async def find_climatology(self, key: dict[str, Any]) -> dict[str, Any] | None:
        return await self._records.find_one({**key, "kind": "climatology"})

    async def save_climatology(self, key: dict[str, Any], doc: dict[str, Any]) -> str:
        async def save() -> dict[str, Any]:
            return await self._records.find_one_and_replace(
                {**key, "kind": "climatology"}, doc, upsert=True, return_document=ReturnDocument.AFTER,
            )
        saved = await _retry_on_race(save)
        return str(saved["_id"])

    async def find_current(self, key: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        # The TTL monitor runs about once a minute, so also filter on expiry here.
        return await self._records.find_one({**key, "kind": "current", "expires_at": {"$gt": now}})

    async def save_current(self, key: dict[str, Any], doc: dict[str, Any]) -> None:
        await _retry_on_race(lambda: self._records.replace_one({**key, "kind": "current"}, doc, upsert=True))

    async def find_forecast(self, key: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        return await self._forecasts.find_one({**key, "expires_at": {"$gt": now}})

    async def save_forecast(self, key: dict[str, Any], doc: dict[str, Any]) -> None:
        await self._forecasts.replace_one(key, doc, upsert=True)


async def _retry_on_race(save):  # type: ignore[no-untyped-def]
    """Two requests can upsert the same cache key at once; the loser hits the unique index.
    Retrying once then matches the winner's document and replaces it."""
    try:
        return await save()
    except DuplicateKeyError:
        return await save()


class NoCacheWeatherRepo:
    """Used when MongoDB is not configured: every request goes to the provider."""

    async def find_climatology(self, key: dict[str, Any]) -> dict[str, Any] | None:
        return None

    async def save_climatology(self, key: dict[str, Any], doc: dict[str, Any]) -> str:
        return ""

    async def find_current(self, key: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        return None

    async def save_current(self, key: dict[str, Any], doc: dict[str, Any]) -> None:
        return None

    async def find_forecast(self, key: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        return None

    async def save_forecast(self, key: dict[str, Any], doc: dict[str, Any]) -> None:
        return None
