import httpx
import pytest
import respx

from app.core.settings import Settings
from app.integrations.tiles.base import TileNotFound, TilesUnavailable, UnconfiguredTiles
from app.integrations.tiles.factory import build_tile_provider
from app.integrations.tiles.mock import MockTiles
from app.integrations.tiles.raster import RasterTiles
from tests.integration.journey import PIN_LAT, PIN_LON, create_property, create_user

TEMPLATE = "https://tiles.example/World_Imagery/MapServer/tile/{z}/{y}/{x}"  # Esri-style: row before column


def esri_like(http, key="secret-key"):
    return RasterTiles(http, name="Test", url_template=TEMPLATE, key_param="token", api_key=key, attribution="credit")
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


class FakeTiles:
    is_mock = False
    attribution = "Test imagery credit"
    max_zoom = 19

    def __init__(self):
        self.calls = []

    async def get_tile(self, z, x, y):
        from app.integrations.tiles.base import Tile
        self.calls.append((z, x, y))
        return Tile(JPEG, "image/jpeg")


# --- /api/map/config -----------------------------------------------------------------------

def test_config_without_a_key_says_so(api):
    body = api.client.get("/api/map/config").json()
    assert body["satellite_available"] is False and "MAPTILER_API_KEY" in body["detail"]
    assert body["tile_url"] == "/api/tiles/satellite/{z}/{x}/{y}"


def test_config_with_tiles_gives_the_credit_line(api):
    api.client.app.state.tiles = FakeTiles()
    body = api.client.get("/api/map/config").json()
    assert body == {"satellite_available": True, "tile_url": "/api/tiles/satellite/{z}/{x}/{y}",
                    "attribution": "Test imagery credit", "max_zoom": 19, "is_mock": False, "detail": None}


def test_mock_tiles_are_labelled(api):
    api.client.app.state.tiles = MockTiles()
    assert api.client.get("/api/map/config").json()["is_mock"] is True
    r = api.client.get("/api/tiles/satellite/3/5/3")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:4] == b"\x89PNG"


# --- /api/tiles/satellite -----------------------------------------------------------------------

def test_tile_is_proxied_and_cacheable(api):
    tiles = FakeTiles()
    api.client.app.state.tiles = tiles
    r = api.client.get("/api/tiles/satellite/17/93112/54580")
    assert r.status_code == 200 and r.content == JPEG
    assert r.headers["content-type"] == "image/jpeg" and "max-age" in r.headers["cache-control"]
    assert tiles.calls == [(17, 93112, 54580)]


@pytest.mark.parametrize("path", ["2/4/0", "2/0/4", "20/0/0", "-1/0/0"])
def test_tiles_outside_the_grid_are_rejected(api, path):
    api.client.app.state.tiles = FakeTiles()
    assert api.client.get(f"/api/tiles/satellite/{path}").status_code in (404, 422)
    assert api.client.app.state.tiles.calls == []


def test_tile_without_a_key_is_503(api):
    r = api.client.get("/api/tiles/satellite/1/0/0")
    assert r.status_code == 503 and r.json()["error"]["code"] == "tiles_unavailable"


# --- provider choice ---------------------------------------------------------------------------

def _provider(**settings):
    return build_tile_provider(Settings(_env_file=None, **settings), httpx.AsyncClient())


def test_maptiler_is_the_default():
    tiles = _provider(maptiler_api_key="mt-key")
    assert isinstance(tiles, RasterTiles) and tiles.name == "MapTiler" and "MapTiler" in tiles.attribution


def test_esri_can_be_chosen():
    tiles = _provider(map_tiles_provider="esri", esri_api_key="e-key")
    assert isinstance(tiles, RasterTiles) and tiles.name == "Esri"


@pytest.mark.parametrize("settings, missing", [
    ({}, "MAPTILER_API_KEY"),
    ({"map_tiles_provider": "esri", "maptiler_api_key": "mt-key"}, "ESRI_API_KEY"),
    ({"maptiler_api_key": "<from-maptiler>"}, "MAPTILER_API_KEY"),  # placeholder copied from .env.example
    ({"map_tiles_provider": "google", "maptiler_api_key": "k"}, "unknown"),
])
def test_missing_key_or_provider_leaves_the_map_without_imagery(settings, missing):
    tiles = _provider(**settings)
    assert isinstance(tiles, UnconfiguredTiles) and missing in tiles.reason


def test_mock_wins_over_keys():
    assert isinstance(_provider(use_mock_tiles=True, maptiler_api_key="k"), MockTiles)


@respx.mock
async def test_maptiler_url_and_key():
    route = respx.get("https://api.maptiler.com/maps/satellite/256/17/93112/54580.jpg").mock(
        return_value=httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"}))
    async with httpx.AsyncClient() as http:
        tiles = build_tile_provider(Settings(_env_file=None, maptiler_api_key="mt-key"), http)
        tile = await tiles.get_tile(17, 93112, 54580)
    assert tile.content == JPEG and route.calls.last.request.url.params["key"] == "mt-key"


# --- raster adapter ------------------------------------------------------------------------------

@respx.mock
async def test_template_order_and_key_param_are_respected():
    route = respx.get("https://tiles.example/World_Imagery/MapServer/tile/17/54580/93112").mock(
        return_value=httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"}))
    async with httpx.AsyncClient() as http:
        tile = await esri_like(http).get_tile(17, 93112, 54580)
    assert tile.content == JPEG and route.calls.last.request.url.params["token"] == "secret-key"


@respx.mock
@pytest.mark.parametrize("response, error", [
    (httpx.Response(404), TileNotFound),
    (httpx.Response(403), TilesUnavailable),
    (httpx.Response(429), TilesUnavailable),  # e.g. MapTiler free plan paused for the month
    (httpx.Response(500), TilesUnavailable),
    # ArcGIS reports a bad token as HTTP 200 with a JSON error body.
    (httpx.Response(200, json={"error": {"code": 498, "message": "Invalid token."}}), TilesUnavailable),
])
async def test_provider_errors(response, error):
    respx.get(url__startswith="https://tiles.example/").mock(return_value=response)
    async with httpx.AsyncClient() as http:
        with pytest.raises(error) as exc:
            await esri_like(http).get_tile(1, 0, 0)
    assert "secret-key" not in exc.value.message


@respx.mock
async def test_one_timeout_is_retried():
    route = respx.get(url__startswith="https://tiles.example/").mock(
        side_effect=[httpx.ReadTimeout("cold"), httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})])
    async with httpx.AsyncClient() as http:
        tile = await esri_like(http).get_tile(1, 0, 0)
    assert tile.content == JPEG and route.call_count == 2


@respx.mock
async def test_timeout_is_retryable():
    respx.get(url__startswith="https://tiles.example/").mock(side_effect=httpx.ConnectTimeout("slow"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(TilesUnavailable) as exc:
            await esri_like(http, key="k").get_tile(1, 0, 0)
    assert exc.value.retryable


# --- saved pins --------------------------------------------------------------------------------

def test_saved_pin_can_be_read_back(api):
    user_id = create_user(api.client)
    r = api.client.post("/api/properties", json={"user_id": user_id, "lat": PIN_LAT, "lon": PIN_LON,
                                                  "address_text": "Test address"})
    body = api.client.get(f"/api/properties/{r.json()['property_id']}").json()
    assert body["user_id"] == user_id and body["address_text"] == "Test address"
    assert (body["lat"], body["lon"]) == (PIN_LAT, PIN_LON) and body["grid_key"] == r.json()["grid_key"]


def test_latest_property_is_the_newest_pin(api):
    user_id = create_user(api.client)
    create_property(api.client, user_id)
    newest = create_property(api.client, user_id)
    assert api.client.get(f"/api/users/{user_id}").json()["latest"]["property_id"] == newest


def test_unknown_property_is_404(api):
    r = api.client.get("/api/properties/" + "a" * 24)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
