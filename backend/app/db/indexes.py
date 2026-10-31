"""Index definitions, created at app startup."""

import logging

from pymongo import ASCENDING, DESCENDING, GEOSPHERE, IndexModel
from pymongo.asynchronous.database import AsyncDatabase

from app.db import collections as c

log = logging.getLogger(__name__)

AGENT_LOG_TTL_SECONDS = 30 * 24 * 60 * 60

INDEXES: dict[str, list[IndexModel]] = {
    c.PROPERTIES: [
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_latest"),
        IndexModel([("pin", GEOSPHERE)], name="pin_2dsphere"),
    ],
    c.ROOF_ASSESSMENTS: [
        IndexModel([("property_id", ASCENDING), ("created_at", DESCENDING)], name="property_latest"),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_latest"),
    ],
    c.WEATHER_RECORDS: [
        IndexModel(
            [
                ("grid_key", ASCENDING),
                ("kind", ASCENDING),
                ("tilt_deg", ASCENDING),
                ("azimuth_deg", ASCENDING),
                ("period", ASCENDING),
            ],
            name="cache_key",
            unique=True,
        ),
        IndexModel([("expires_at", ASCENDING)], name="expires_at_ttl", expireAfterSeconds=0),
    ],
    c.WEATHER_FORECASTS: [
        IndexModel(
            [("grid_key", ASCENDING), ("tilt_deg", ASCENDING), ("azimuth_deg", ASCENDING)],
            name="cache_key",
        ),
        IndexModel([("expires_at", ASCENDING)], name="expires_at_ttl", expireAfterSeconds=0),
    ],
    c.SOLAR_ESTIMATES: [
        IndexModel([("property_id", ASCENDING), ("created_at", DESCENDING)], name="property_latest"),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_latest"),
    ],
    c.POLICY_RECORDS: [
        IndexModel([("scheme_id", ASCENDING), ("verified_on", DESCENDING)], name="scheme_latest"),
        IndexModel([("status", ASCENDING)], name="status"),
    ],
    c.APPLICATIONS: [
        IndexModel([("user_id", ASCENDING)], name="user_id"),
    ],
    c.AGENT_LOGS: [
        IndexModel([("run_id", ASCENDING)], name="run_id"),
        IndexModel(
            [("created_at", ASCENDING)],
            name="created_at_ttl",
            expireAfterSeconds=AGENT_LOG_TTL_SECONDS,
        ),
    ],
}


async def ensure_indexes(db: AsyncDatabase) -> None:
    for collection, models in INDEXES.items():
        await db[collection].create_indexes(models)
    log.info("MongoDB indexes ensured on %d collections", len(INDEXES))
