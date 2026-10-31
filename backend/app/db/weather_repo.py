"""Weather cache storage. Documents follow docs/DATABASE_SCHEMA.md."""

from datetime import datetime
from typing import Any, Protocol

from pymongo import ReturnDocument
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
        saved = await self._records.find_one_and_replace(
            {**key, "kind": "climatology"},
            doc,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return str(saved["_id"])

    async def find_current(self, key: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        # The TTL monitor runs about once a minute, so also filter on expiry here.
        return await self._records.find_one({**key, "kind": "current", "expires_at": {"$gt": now}})

    async def save_current(self, key: dict[str, Any], doc: dict[str, Any]) -> None:
        await self._records.replace_one({**key, "kind": "current"}, doc, upsert=True)

    async def find_forecast(self, key: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        return await self._forecasts.find_one({**key, "expires_at": {"$gt": now}})

    async def save_forecast(self, key: dict[str, Any], doc: dict[str, Any]) -> None:
        await self._forecasts.replace_one(key, doc, upsert=True)


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
