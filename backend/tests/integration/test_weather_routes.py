import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app

Q = "lat=28.61&lon=77.21&tilt=20&azimuth=0"


@pytest.fixture(scope="module")
def client():
    # Mock weather, no MongoDB: runs offline and every response must say it is a mock.
    with TestClient(create_app(Settings(_env_file=None, use_mock_weather=True))) as c:
        yield c


def test_climatology_from_mock(client):
    r = client.get(f"/api/weather/climatology?{Q}")
    assert r.status_code == 200
    body = r.json()
    assert body["is_mock"] is True
    assert any("Mock" in n for n in body["notes"])
    assert len(body["monthly"]) == 12 and len(body["years"]) == 10
    assert body["monthly"][5]["gti_kwh_m2"]["median"] > 0
    # Every mock year is the same recorded year, so the range collapses.
    june = body["monthly"][5]["gti_kwh_m2"]
    assert june["p10"] == june["median"] == june["p90"]


def test_current_from_mock(client):
    body = client.get("/api/weather/current?lat=28.61&lon=77.21").json()
    assert body["is_mock"] is True
    assert body["observation"]["temperature_c"] is not None


def test_forecast_from_mock(client):
    body = client.get(f"/api/weather/forecast?{Q}").json()
    assert body["label"] == "Short-term outlook"
    assert body["is_mock"] is True
    assert len(body["daily"]) == 7


def test_outside_delhi_is_422(client):
    r = client.get("/api/weather/climatology?lat=19.07&lon=72.88&tilt=20&azimuth=0")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "outside_delhi"


@pytest.mark.parametrize("q", ["lat=28.61&lon=77.21&tilt=95&azimuth=0", "lat=28.61&lon=77.21&tilt=20&azimuth=200", "lat=28.61&lon=77.21"])
def test_bad_parameters_are_422(client, q):
    r = client.get(f"/api/weather/climatology?{q}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"
