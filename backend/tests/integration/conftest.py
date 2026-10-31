from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_store, weather_repo
from app.core.settings import Settings
from app.main import create_app
from app.db import collections as c
from app.db.seed import load_policy_records, load_procedures, policy_doc
from app.integrations.meko.mock import MockMemoryProvider
from tests.fakes import FakeGeocoder, FakeLLM, FakeWeatherProvider, FakeWeatherRepo, MemoryStore
from tests.weather_data import JOURNEY_READY, assumptions


@dataclass
class Api:
    client: TestClient
    store: MemoryStore
    weather: FakeWeatherProvider
    geocoder: FakeGeocoder
    llm: FakeLLM
    memory: MockMemoryProvider

    def set_assumptions(self, **sections):
        self.client.app.state.assumptions = assumptions(**{**JOURNEY_READY, **sections})


def seed(store: MemoryStore) -> None:
    """The real seed records, with review dates moved far out so tests do not expire with the calendar."""
    for rec in load_policy_records():
        doc = policy_doc(rec)
        if doc["status"] == "verified":
            doc["review_by"] = "2099-12-31"
        store.data.setdefault(c.POLICY_RECORDS, {})[f"{len(store.data.get(c.POLICY_RECORDS, {})):024x}"] = doc
    for i, p in enumerate(load_procedures()):
        store.data.setdefault(c.PROCEDURES, {})[f"{i:024x}"] = p.model_dump()


@pytest.fixture
def api():
    """The real app with MongoDB, weather and geocoding replaced by in-memory fakes."""
    app = create_app(Settings(_env_file=None))
    store, repo = MemoryStore(), FakeWeatherRepo()
    seed(store)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[weather_repo] = lambda: repo
    with TestClient(app) as client:
        weather, geocoder, llm, memory = FakeWeatherProvider(), FakeGeocoder(), FakeLLM(), MockMemoryProvider()
        app.state.weather_provider = weather
        app.state.geocoder = geocoder
        app.state.llm = llm
        app.state.memory = memory
        app.state.assumptions = assumptions(**JOURNEY_READY)
        yield Api(client, store, weather, geocoder, llm, memory)
