from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_store, weather_repo
from app.core.settings import Settings
from app.main import create_app
from tests.fakes import FakeGeocoder, FakeWeatherProvider, FakeWeatherRepo, MemoryStore
from tests.weather_data import JOURNEY_READY, assumptions


@dataclass
class Api:
    client: TestClient
    store: MemoryStore
    weather: FakeWeatherProvider
    geocoder: FakeGeocoder

    def set_assumptions(self, **sections):
        self.client.app.state.assumptions = assumptions(**{**JOURNEY_READY, **sections})


@pytest.fixture
def api():
    """The real app with MongoDB, weather and geocoding replaced by in-memory fakes."""
    app = create_app(Settings(_env_file=None))
    store, repo = MemoryStore(), FakeWeatherRepo()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[weather_repo] = lambda: repo
    with TestClient(app) as client:
        weather, geocoder = FakeWeatherProvider(), FakeGeocoder()
        app.state.weather_provider = weather
        app.state.geocoder = geocoder
        app.state.assumptions = assumptions(**JOURNEY_READY)
        yield Api(client, store, weather, geocoder)
