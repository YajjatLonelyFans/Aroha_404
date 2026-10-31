from app.db import collections as c
from app.db.indexes import AGENT_LOG_TTL_SECONDS, INDEXES


def _doc(collection: str, name: str) -> dict:
    return next(m.document for m in INDEXES[collection] if m.document["name"] == name)


def test_weather_cache_key_is_unique():
    idx = _doc(c.WEATHER_RECORDS, "cache_key")
    assert idx["unique"] is True
    assert list(idx["key"]) == ["grid_key", "kind", "tilt_deg", "azimuth_deg", "period"]


def test_ttl_indexes():
    assert _doc(c.WEATHER_RECORDS, "expires_at_ttl")["expireAfterSeconds"] == 0
    assert _doc(c.WEATHER_FORECASTS, "expires_at_ttl")["expireAfterSeconds"] == 0
    assert _doc(c.AGENT_LOGS, "created_at_ttl")["expireAfterSeconds"] == AGENT_LOG_TTL_SECONDS
    assert AGENT_LOG_TTL_SECONDS == 30 * 86400


def test_latest_lookups_sort_newest_first():
    for coll in (c.ROOF_ASSESSMENTS, c.SOLAR_ESTIMATES):
        assert dict(_doc(coll, "property_latest")["key"]) == {"property_id": 1, "created_at": -1}


def test_users_has_no_extra_indexes():
    assert c.USERS not in INDEXES
