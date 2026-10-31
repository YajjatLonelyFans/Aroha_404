from datetime import date

import httpx
import pytest
import respx

from app.integrations.weather.base import WeatherRequestRejected, WeatherUnavailable
from app.integrations.weather.open_meteo import OpenMeteoProvider
from tests.weather_data import hourly_body

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"


@pytest.fixture
async def provider():
    async with httpx.AsyncClient() as client:
        yield OpenMeteoProvider(client, ARCHIVE, FORECAST, backoff_s=0)


@respx.mock
async def test_history_request_and_parse(provider):
    route = respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=hourly_body(date(2024, 1, 1), date(2024, 1, 2))))
    s = await provider.hourly_history(28.61, 77.21, 20, 0, date(2024, 1, 1), date(2024, 1, 2))
    params = route.calls.last.request.url.params
    assert params["tilt"] == "20" and params["azimuth"] == "0"
    assert params["timezone"] == "Asia/Kolkata"
    assert params["start_date"] == "2024-01-01" and params["end_date"] == "2024-01-02"
    assert "global_tilted_irradiance" in params["hourly"]
    assert len(s.times) == 48 and len(s.values["global_tilted_irradiance"]) == 48
    assert s.source.is_mock is False and s.source.retrieved_at.tzinfo is not None


@respx.mock
async def test_missing_variable_becomes_none(provider):
    body = hourly_body(date(2024, 1, 1), date(2024, 1, 1))
    del body["hourly"]["cloud_cover"]
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=body))
    s = await provider.hourly_history(28.61, 77.21, 20, 0, date(2024, 1, 1), date(2024, 1, 1))
    assert s.values["cloud_cover"] == [None] * 24


@respx.mock
async def test_server_error_is_retried_then_succeeds(provider):
    route = respx.get(FORECAST).mock(side_effect=[
        httpx.Response(503),
        httpx.Response(200, json={"current": {"time": "2026-11-01T12:00", "temperature_2m": 24}, "current_units": {}}),
    ])
    cur = await provider.current(28.61, 77.21)
    assert route.call_count == 2
    assert cur.values["temperature_2m"] == 24
    assert cur.values["cloud_cover"] is None


@respx.mock
async def test_persistent_server_error_is_unavailable(provider):
    route = respx.get(FORECAST).mock(return_value=httpx.Response(500))
    with pytest.raises(WeatherUnavailable):
        await provider.current(28.61, 77.21)
    assert route.call_count == 3  # 1 try + 2 retries


@respx.mock
async def test_timeout_is_retried_and_reported(provider):
    route = respx.get(FORECAST).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(WeatherUnavailable) as exc:
        await provider.forecast(28.61, 77.21, 20, 0)
    assert exc.value.retryable
    assert route.call_count == 3


@respx.mock
async def test_client_error_is_not_retried(provider):
    route = respx.get(ARCHIVE).mock(return_value=httpx.Response(400, json={"error": True, "reason": "Invalid tilt"}))
    with pytest.raises(WeatherRequestRejected) as exc:
        await provider.hourly_history(28.61, 77.21, 95, 0, date(2024, 1, 1), date(2024, 1, 1))
    assert route.call_count == 1
    assert "Invalid tilt" in exc.value.message
