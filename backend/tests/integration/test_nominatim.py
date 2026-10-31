import httpx
import pytest
import respx

from app.integrations.geocoding.base import GeocodingUnavailable
from app.integrations.geocoding.mock import MockGeocoder
from app.integrations.geocoding.nominatim import NominatimGeocoder

URL = "https://nominatim.openstreetmap.org/search"
BBOX = (76.83, 28.40, 77.35, 28.89)
UA = "Aroha-Test/0.1 (contact: test@example.com)"
ROW = {"display_name": "Connaught Place, New Delhi", "lat": "28.63", "lon": "77.22", "category": "place", "type": "suburb"}


class FakeTime:
    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def clock(self):
        return self.now

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
async def geo():
    t = FakeTime()
    async with httpx.AsyncClient() as client:
        yield NominatimGeocoder(client, "https://nominatim.openstreetmap.org", UA, clock=t.clock, sleep=t.sleep), t


@respx.mock
async def test_request_follows_usage_policy(geo):
    g, _ = geo
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=[ROW]))
    result = await g.search("Connaught Place", BBOX)
    req = route.calls.last.request
    assert req.headers["User-Agent"] == UA
    p = req.url.params
    assert p["format"] == "jsonv2" and p["countrycodes"] == "in" and p["bounded"] == "1"
    assert p["viewbox"] == "76.83,28.89,77.35,28.4"
    assert result.places[0].lat == 28.63 and result.places[0].lon == 77.22
    assert result.source.is_mock is False


@respx.mock
async def test_repeat_queries_are_cached(geo):
    g, _ = geo
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=[ROW]))
    await g.search("Connaught Place", BBOX)
    again = await g.search("  connaught   PLACE ", BBOX)
    assert route.call_count == 1 and again.cached is True


@respx.mock
async def test_requests_are_spaced_one_second_apart(geo):
    g, t = geo
    respx.get(URL).mock(return_value=httpx.Response(200, json=[ROW]))
    await g.search("first place", BBOX)
    t.now += 0.3
    await g.search("second place", BBOX)
    assert t.slept == [pytest.approx(0.7)]


@respx.mock
async def test_rate_limited_is_unavailable(geo):
    g, _ = geo
    respx.get(URL).mock(return_value=httpx.Response(429))
    with pytest.raises(GeocodingUnavailable) as exc:
        await g.search("Connaught Place", BBOX)
    assert "pin" in exc.value.message


@respx.mock
async def test_network_error_is_unavailable(geo):
    g, _ = geo
    respx.get(URL).mock(side_effect=httpx.ConnectError("offline"))
    with pytest.raises(GeocodingUnavailable):
        await g.search("Connaught Place", BBOX)


async def test_mock_geocoder_is_labelled():
    result = await MockGeocoder().search("Sukhdev college", BBOX)
    assert result.source.is_mock is True
    assert "Shaheed Sukhdev" in result.places[0].display_name
