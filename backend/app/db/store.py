"""Small document store used by the user, property, roof and solar services.

Documents come back with their id as a string under "id" (not "_id").
"""

from typing import Any, Protocol

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import DESCENDING
from pymongo.asynchronous.database import AsyncDatabase


class DocumentStore(Protocol):
    async def insert(self, collection: str, doc: dict[str, Any]) -> str: ...
    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None: ...
    async def latest(self, collection: str, filter: dict[str, Any]) -> dict[str, Any] | None: ...
    async def update(self, collection: str, doc_id: str, fields: dict[str, Any]) -> None: ...
    async def find(self, collection: str, filter: dict[str, Any]) -> list[dict[str, Any]]: ...


def _oid(doc_id: str) -> ObjectId | None:
    try:
        return ObjectId(doc_id)
    except (InvalidId, TypeError):
        return None


def _out(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


class MongoStore:
    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db

    async def insert(self, collection: str, doc: dict[str, Any]) -> str:
        result = await self._db[collection].insert_one(dict(doc))
        return str(result.inserted_id)

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        oid = _oid(doc_id)
        if oid is None:
            return None
        return _out(await self._db[collection].find_one({"_id": oid}))

    async def latest(self, collection: str, filter: dict[str, Any]) -> dict[str, Any] | None:
        return _out(await self._db[collection].find_one(filter, sort=[("created_at", DESCENDING)]))

    async def update(self, collection: str, doc_id: str, fields: dict[str, Any]) -> None:
        oid = _oid(doc_id)
        if oid is not None:
            await self._db[collection].update_one({"_id": oid}, {"$set": fields})

    async def find(self, collection: str, filter: dict[str, Any]) -> list[dict[str, Any]]:
        return [_out(doc) async for doc in self._db[collection].find(filter)]
