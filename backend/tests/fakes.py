"""In-memory stand-ins for MongoDB and the external services, shared by tests."""

import copy
import itertools
from datetime import date, datetime, timedelta, timezone

from app.integrations.common import SourceInfo
from app.integrations.geocoding.base import GeocodeResult, GeocodingUnavailable, Place
from app.integrations.weather.base import WeatherUnavailable
from tests.weather_data import current_conditions, series


class MemoryStore:
    """DocumentStore in a dict. Ids look like Mongo ObjectIds."""

    def __init__(self):
        self.data: dict[str, dict[str, dict]] = {}
        self._ids = itertools.count(1)

    async def insert(self, collection, doc):
        doc_id = f"{next(self._ids):024x}"
        self.data.setdefault(collection, {})[doc_id] = copy.deepcopy(doc)
        return doc_id

    async def get(self, collection, doc_id):
        doc = self.data.get(collection, {}).get(doc_id)
        return None if doc is None else {**copy.deepcopy(doc), "id": doc_id}

    async def latest(self, collection, filter):
        rows = [
            (doc_id, doc) for doc_id, doc in self.data.get(collection, {}).items()
            if all(doc.get(k) == v for k, v in filter.items())
        ]
        if not rows:
            return None
        doc_id, doc = max(rows, key=lambda r: (r[1]["created_at"], r[0]))
        return {**copy.deepcopy(doc), "id": doc_id}

    async def update(self, collection, doc_id, fields):
        if doc_id in self.data.get(collection, {}):
            self.data[collection][doc_id].update(copy.deepcopy(fields))


class FakeWeatherRepo:
    """In-memory stand-in for MongoWeatherRepo."""

    def __init__(self):
        self.climatology, self.current_docs, self.forecasts = {}, {}, {}
        self.saves = 0

    @staticmethod
    def _k(key):
        return tuple(sorted(key.items()))

    async def find_climatology(self, key):
        return copy.deepcopy(self.climatology.get(self._k(key)))

    async def save_climatology(self, key, doc):
        self.saves += 1
        stored = copy.deepcopy(doc)
        stored["_id"] = f"clim-{self.saves}"
        self.climatology[self._k(key)] = stored
        return stored["_id"]

    async def find_current(self, key, now):
        doc = self.current_docs.get(self._k(key))
        return copy.deepcopy(doc) if doc and doc["expires_at"] > now else None

    async def save_current(self, key, doc):
        self.current_docs[self._k(key)] = copy.deepcopy(doc)

    async def find_forecast(self, key, now):
        doc = self.forecasts.get(self._k(key))
        return copy.deepcopy(doc) if doc and doc["expires_at"] > now else None

    async def save_forecast(self, key, doc):
        self.forecasts[self._k(key)] = copy.deepcopy(doc)


class FakeWeatherProvider:
    """Synthetic weather: 12 sunny hours a day at `gti_day` W/m², 25 °C."""

    def __init__(self, is_mock=False, fail=False, gti_day=500.0):
        self.is_mock = is_mock
        self.fail = fail
        self.gti_day = gti_day
        self.calls = {"history": 0, "current": 0, "forecast": 0}
        self.history_args = None

    async def hourly_history(self, lat, lon, tilt, azimuth, start, end):
        self.calls["history"] += 1
        self.history_args = (lat, lon, tilt, azimuth, start, end)
        if self.fail:
            raise WeatherUnavailable("down")
        return series(start, end, is_mock=self.is_mock, gti_day=self.gti_day)

    async def current(self, lat, lon):
        self.calls["current"] += 1
        if self.fail:
            raise WeatherUnavailable("down")
        return current_conditions(self.is_mock)

    async def forecast(self, lat, lon, tilt, azimuth, days=7):
        self.calls["forecast"] += 1
        if self.fail:
            raise WeatherUnavailable("down")
        return series(date(2026, 11, 1), date(2026, 11, 1) + timedelta(days=days - 1), is_mock=self.is_mock)


class FakeLLM:
    """Scripted LLM. By default it repeats the first fact it is given (numbers stay valid)."""

    is_mock = False
    model = "fake-llm"

    def __init__(self, replies=None, error=None):
        self.replies = list(replies or [])
        self.error = error
        self.prompts: list[str] = []

    async def generate(self, *, system, prompt, max_output_tokens=700, temperature=0.2):
        from app.integrations.llm.base import LLMReply
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        if self.replies:
            return LLMReply(text=self.replies.pop(0), model=self.model)
        first_fact = next((line[2:] for line in prompt.splitlines() if line.startswith("- ")), "Nothing yet.")
        return LLMReply(text=f"Here you go: {first_fact}", model=self.model)


class FailingMemory:
    is_mock = False

    def session(self):
        from contextlib import asynccontextmanager

        from app.integrations.meko.base import MemoryUnavailable

        @asynccontextmanager
        async def _session():
            raise MemoryUnavailable("The memory service is not reachable.")
            yield  # pragma: no cover

        return _session()


class FakeGeocoder:
    is_mock = False

    def __init__(self, places=None, fail=False):
        self.places = places if places is not None else [
            Place("Connaught Place, New Delhi, Delhi, 110001, India", 28.6317695, 77.2193804, "place", "suburb"),
            Place("Somewhere outside Delhi", 19.07, 72.88, "place", "city"),
        ]
        self.fail = fail
        self.queries = []

    async def search(self, query, bbox, limit=5):
        self.queries.append(query)
        if self.fail:
            raise GeocodingUnavailable("down")
        src = SourceInfo("Test geocoder", "test://geo", datetime(2026, 11, 1, tzinfo=timezone.utc))
        return GeocodeResult(self.places[:limit], src)
