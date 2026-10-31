"""Mock address search for offline development. Every result has is_mock=True.

Replays search results recorded from Nominatim (tests/fixtures/nominatim_search.json),
keeping places whose name contains a word of the query, or all of them if none match.
"""

import json
from datetime import datetime, timezone
from functools import lru_cache

from app.core.settings import BACKEND_DIR
from app.integrations.common import SourceInfo
from app.integrations.geocoding.base import Bbox, GeocodeResult, Place

FIXTURE = BACKEND_DIR / "tests" / "fixtures" / "nominatim_search.json"


@lru_cache
def _places() -> list[Place]:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [Place(r["display_name"], float(r["lat"]), float(r["lon"]), r.get("category"), r.get("type")) for r in rows]


class MockGeocoder:
    is_mock = True

    async def search(self, query: str, bbox: Bbox, limit: int = 5) -> GeocodeResult:
        words = [w for w in query.lower().split() if len(w) > 2]
        matches = [p for p in _places() if any(w in p.display_name.lower() for w in words)]
        source = SourceInfo("Mock address search (recorded Nominatim data, not live)", "mock://geocoding",
                            datetime.now(timezone.utc), is_mock=True)
        return GeocodeResult((matches or _places())[:limit], source)
