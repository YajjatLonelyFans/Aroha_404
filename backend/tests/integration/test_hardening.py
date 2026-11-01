import asyncio

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.api.deps import get_store
from app.core.assumptions import load_assumptions
from app.core.ratelimit import ChatLimiter, RateLimited, SlidingWindowLimiter
from app.core.settings import Settings
from app.integrations.llm.gemini import GEMINI_URL
from app.integrations.meko.mock import MockMemoryProvider
from app.services.health_service import check_health
from tests.fakes import FailingMemory
from tests.integration.test_assistant_routes import chat, ready_user


class BrokenStore:
    def __init__(self, exc):
        self.exc = exc

    async def get(self, *a, **k):
        raise self.exc

    latest = insert = update = find = get


# --- error envelopes ------------------------------------------------------------------------

def test_database_outage_is_a_clean_503(api):
    api.client.app.dependency_overrides[get_store] = lambda: BrokenStore(ServerSelectionTimeoutError("no primary"))
    r = api.client.get("/api/users/" + "a" * 24)
    assert r.status_code == 503
    assert r.json()["error"] == {"code": "database_unavailable", "retryable": True,
                                 "message": "The database is not responding. Try again shortly."}


def test_unexpected_error_hides_internals(api):
    api.client.app.dependency_overrides[get_store] = lambda: BrokenStore(RuntimeError("secret detail"))
    client = TestClient(api.client.app, raise_server_exceptions=False)
    r = client.get("/api/users/" + "a" * 24)
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "secret detail" not in r.text


def test_responses_carry_timing(api):
    r = api.client.get("/api/health")
    assert int(r.headers["X-Response-Time-ms"]) >= 0


# --- chat speed and quota guards ---------------------------------------------------------------

class SlowMemory(MockMemoryProvider):
    """Mock memory whose search takes longer than the recall budget."""

    def session(self):
        cm = super().session()
        outer = self

        class Wrap:
            async def __aenter__(self):
                s = await cm.__aenter__()

                async def slow_search(*a, **k):
                    await asyncio.sleep(outer.delay)
                    return []
                s.search = slow_search
                return s

            async def __aexit__(self, *exc):
                return await cm.__aexit__(*exc)
        return Wrap()


def test_slow_recall_is_cut_off_but_records_still_resume(api):
    memory = SlowMemory()
    memory.delay = 2.0
    api.client.app.state.memory = memory
    api.client.app.state.settings.meko_recall_timeout_s = 0.2
    user_id = ready_user(api)
    body = chat(api, user_id, "Hi, where was I?")
    assert any("recall was slow" in n for n in body["notes"])
    assert body["memory"]["recalled"] == 0 and body["memory"]["error"] is None
    assert all(o["status"] == "ok" for o in body["agent_outputs"])  # saved records were used
    assert "don't have your home's details" not in body["reply"]


def test_chat_is_rate_limited_per_user(api):
    api.client.app.state.chat_limiter = ChatLimiter(per_user=2, total=100)
    user_id = ready_user(api)
    chat(api, user_id, "How many panels fit?")
    chat(api, user_id, "How many panels fit?")
    r = api.client.post("/api/assistant/chat", json={"user_id": user_id, "message": "again?"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited" and r.json()["error"]["details"]["retry_after_s"] > 0
    other = ready_user(api)
    assert api.client.post("/api/assistant/chat", json={"user_id": other, "message": "hi"}).status_code == 200


def test_limiter_window_slides():
    now = [0.0]
    limiter = SlidingWindowLimiter(2, window_s=60, clock=lambda: now[0])
    limiter.check("u"); limiter.check("u")
    with pytest.raises(RateLimited):
        limiter.check("u")
    now[0] = 61
    limiter.check("u")  # the old events have left the window


# --- deep health -----------------------------------------------------------------------------

SETTINGS = dict(_env_file=None, llm_provider="gemini", llm_api_key="k", llm_model="gemini-3.5-flash-lite",
                meko_api_key="m")


@respx.mock
async def test_deep_health_checks_gemini_without_generating():
    route = respx.get(f"{GEMINI_URL}/models/gemini-3.5-flash-lite").mock(return_value=httpx.Response(200, json={}))
    respx.get(url__startswith="https://api.open-meteo.com").mock(return_value=httpx.Response(200, json={}))
    h = await check_health(Settings(**SETTINGS), None, load_assumptions(), deep=True, memory=None)
    assert h.dependencies["llm"].status == "ok"
    assert route.calls.last.request.headers["x-goog-api-key"] == "k"


@respx.mock
async def test_deep_health_reports_bad_gemini_key():
    respx.get(f"{GEMINI_URL}/models/gemini-3.5-flash-lite").mock(return_value=httpx.Response(403))
    respx.get(url__startswith="https://api.open-meteo.com").mock(return_value=httpx.Response(200, json={}))
    h = await check_health(Settings(**SETTINGS), None, load_assumptions(), deep=True)
    assert h.dependencies["llm"].status == "error" and h.dependencies["llm"].detail == "HTTP 403"


@respx.mock
async def test_deep_health_reports_meko_outage():
    respx.get(url__startswith=GEMINI_URL).mock(return_value=httpx.Response(200, json={}))
    respx.get(url__startswith="https://api.open-meteo.com").mock(return_value=httpx.Response(200, json={}))
    h = await check_health(Settings(**SETTINGS), None, load_assumptions(), deep=True, memory=FailingMemory())
    assert h.dependencies["meko"].status == "error"


async def test_shallow_health_makes_no_calls():
    h = await check_health(Settings(**SETTINGS), None, load_assumptions(), deep=False, memory=FailingMemory())
    assert h.dependencies["meko"].status == "configured" and h.dependencies["llm"].status == "configured"


# --- deep checks for address search and imagery ---------------------------------------------

class _Tiles:
    is_mock, attribution, max_zoom = False, "credit", 19

    def __init__(self, fail=False):
        self.fail, self.calls = fail, 0

    async def get_tile(self, z, x, y):
        from app.integrations.tiles.base import Tile, TilesUnavailable
        self.calls += 1
        if self.fail:
            raise TilesUnavailable("Satellite imagery rejected our key.")
        return Tile(b"jpg", "image/jpeg")


DEEP = dict(SETTINGS, nominatim_user_agent="Aroha-test/0.1 (test@example.com)", maptiler_api_key="mt")


@respx.mock
async def test_deep_health_calls_nominatim_status_and_one_tile():
    respx.get(url__startswith=GEMINI_URL).mock(return_value=httpx.Response(200, json={}))
    respx.get(url__startswith="https://api.open-meteo.com").mock(return_value=httpx.Response(200, json={}))
    nominatim = respx.get("https://nominatim.openstreetmap.org/status").mock(return_value=httpx.Response(200, json={}))
    tiles = _Tiles()
    h = await check_health(Settings(**DEEP), None, load_assumptions(), deep=True, tiles=tiles)
    assert h.dependencies["nominatim"].status == "ok" and h.dependencies["satellite_imagery"].status == "ok"
    assert nominatim.calls.last.request.headers["user-agent"].startswith("Aroha-test") and tiles.calls == 1


@respx.mock
async def test_deep_health_reports_failing_imagery():
    respx.get(url__startswith=GEMINI_URL).mock(return_value=httpx.Response(200, json={}))
    respx.get(url__startswith="https://api.open-meteo.com").mock(return_value=httpx.Response(200, json={}))
    respx.get("https://nominatim.openstreetmap.org/status").mock(return_value=httpx.Response(503))
    h = await check_health(Settings(**DEEP), None, load_assumptions(), deep=True, tiles=_Tiles(fail=True))
    assert h.dependencies["satellite_imagery"].status == "error"
    assert "rejected our key" in h.dependencies["satellite_imagery"].detail
    assert h.dependencies["nominatim"].status == "error"


async def test_shallow_health_does_not_fetch_tiles():
    tiles = _Tiles()
    h = await check_health(Settings(**DEEP), None, load_assumptions(), deep=False, tiles=tiles)
    assert h.dependencies["satellite_imagery"].status == "configured" and tiles.calls == 0


# --- a slow search must not throw away the finished ones ---------------------------------------

class OneSlowAgentMemory(MockMemoryProvider):
    """Weather's search outlasts the budget; every other agent answers at once with one note."""

    def session(self):
        cm = super().session()

        class Wrap:
            async def __aenter__(self):
                from app.integrations.meko.base import MemoryHit
                s = await cm.__aenter__()

                async def search(conversation_id, query, agent_ids, k=3):
                    if agent_ids == ["aroha:weather"]:
                        await asyncio.sleep(5)
                    return [MemoryHit(f"m-{agent_ids[0]}", "Prefers the cheaper option.", agent_ids[0], {}, 0.9)]
                s.search = search
                return s

            async def __aexit__(self, *exc):
                return await cm.__aexit__(*exc)
        return Wrap()


def test_slow_search_keeps_the_finished_ones(api):
    api.client.app.state.memory = OneSlowAgentMemory()
    api.client.app.state.settings.meko_recall_timeout_s = 0.5
    user_id = ready_user(api)
    body = chat(api, user_id, "Hi, where was I?")  # a greeting searches all five agents
    assert len(body["agents"]) == 5
    assert body["memory"]["recalled"] == 4, "four agents answered in time; only weather's search was dropped"
    assert any("some earlier notes were skipped" in n for n in body["notes"])
