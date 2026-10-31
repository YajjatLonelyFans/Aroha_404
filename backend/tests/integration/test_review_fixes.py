"""Regression tests for the Stage 7 code-review findings."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError, OperationFailure, ServerSelectionTimeoutError

from app.api.deps import get_store
from app.core.assumptions import load_assumptions
from app.core.ratelimit import ChatLimiter, SlidingWindowLimiter
from app.core.settings import Settings
from app.db.weather_repo import MongoWeatherRepo
from app.integrations.meko.mcp_client import MekoMcpProvider, MekoSession
from app.integrations.meko.mock import MockMemoryProvider
from app.services.health_service import check_health
from tests.integration.journey import create_user
from tests.integration.test_assistant_routes import chat, ready_user


def _tool_result(payload: str):
    return SimpleNamespace(model_dump=lambda by_alias: {"structuredContent": {"result": payload}, "content": [],
                                                        "isError": False})


class FakeMcp:
    """Records call_tool calls and answers memory_search with rows for several agents."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def call_tool(self, name, args):
        import json
        self.calls.append((name, args))
        return _tool_result(json.dumps({"results": self.rows}))


def _row(i, agent, score):
    return {"id": f"m{i}", "memory": f"note {i}", "agent_id": agent, "score": score, "metadata": {}}


# --- 1 & 2: one search per agent, each with its own limit -----------------------------------

async def test_search_runs_per_agent_and_keeps_only_that_agents_rows():
    rows = [_row(1, "aroha:weather", 0.9), _row(2, "aroha:weather", 0.8), _row(3, "aroha:weather", 0.7),
            _row(4, "aroha:roof", 0.3)]
    mcp = FakeMcp(rows)
    provider = MekoMcpProvider("u", "k", "aroha")
    provider.datapack_id = "dp"
    hits = await MekoSession(mcp, provider).search("conv", "q", ["aroha:roof", "aroha:weather"], k=2)
    searched = [args["agent_id"] for name, args in mcp.calls if name == "memory_search"]
    assert sorted(searched) == ["aroha:roof", "aroha:weather"]  # each agent under its own id
    assert all(args["limit"] == 2 for _, args in mcp.calls)  # each agent gets its own k
    by_agent = {}
    for h in hits:
        by_agent.setdefault(h.agent_id, []).append(h.id)
    assert by_agent == {"aroha:weather": ["m1", "m2"], "aroha:roof": ["m4"]}  # roof is not crowded out


# --- 4 & 5: the datapack is resolved once, and a caller's timeout does not cancel it ---------

async def test_datapack_lookup_is_single_flight_and_survives_caller_timeouts():
    provider = MekoMcpProvider("u", "k", "aroha")
    lookups = []

    class FakeSession:
        async def lookup_or_create_datapack(self):
            lookups.append(1)
            await asyncio.sleep(0.05)
            return "dp-1"

    @asynccontextmanager
    async def session():
        yield FakeSession()
    provider.session = session

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(provider.resolve_datapack_id(), 0.01)  # impatient first caller
    results = await asyncio.gather(*[provider.resolve_datapack_id() for _ in range(3)])
    assert results == ["dp-1"] * 3 and len(lookups) == 1 and provider.datapack_id == "dp-1"


# --- 3: a failed record load cancels the recall task ------------------------------------------

class TrackingMemory(MockMemoryProvider):
    def __init__(self, enter_delay=0.0):
        super().__init__()
        self.enter_delay = enter_delay
        self.open_sessions = 0
        self.cancelled = False

    def session(self):
        cm = super().session()
        outer = self

        class Wrap:
            async def __aenter__(self):
                outer.open_sessions += 1
                try:
                    await asyncio.sleep(outer.enter_delay)  # a slow connect
                except asyncio.CancelledError:
                    outer.open_sessions -= 1  # like MekoMcpProvider.session: close on cancel
                    outer.cancelled = True
                    raise
                return await cm.__aenter__()

            async def __aexit__(self, *exc):
                outer.open_sessions -= 1
                return await cm.__aexit__(*exc)
        return Wrap()


def test_failed_record_load_does_not_leave_meko_running(api):
    user_id = ready_user(api)
    memory = TrackingMemory(enter_delay=0.5)
    api.client.app.state.memory = memory
    store = api.store
    real_latest = store.latest

    async def failing_latest(collection, filter):
        raise ServerSelectionTimeoutError("no primary")
    store.latest = failing_latest
    r = api.client.post("/api/assistant/chat", json={"user_id": user_id, "message": "Hi, where was I?"})
    store.latest = real_latest
    assert r.status_code == 503
    assert memory.cancelled  # the recall task was cancelled, not left running
    assert memory.open_sessions == 0  # and its session was closed


def test_recall_budget_covers_connecting(api):
    user_id = ready_user(api)
    api.client.app.state.memory = TrackingMemory(enter_delay=2.0)  # connecting alone is too slow
    api.client.app.state.settings.meko_recall_timeout_s = 0.2
    body = chat(api, user_id, "How many panels fit?")
    assert any("recall was slow" in n for n in body["notes"])
    assert body["agent_outputs"][0]["status"] == "ok"  # still answered from the saved records


# --- 6: unexpected errors keep CORS headers ------------------------------------------------------

class BrokenStore:
    def __init__(self, exc):
        self.exc = exc

    async def get(self, *a, **k):
        raise self.exc

    latest = insert = update = find = get


def test_unexpected_500_keeps_cors_headers(api):
    api.client.app.dependency_overrides[get_store] = lambda: BrokenStore(RuntimeError("secret"))
    client = TestClient(api.client.app, raise_server_exceptions=False)
    r = client.get("/api/users/" + "a" * 24, headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-response-time-ms" in r.headers and "secret" not in r.text


# --- 7: rate limit counts only real users, has a global cap, and stays bounded -------------------

def test_unknown_users_do_not_consume_or_grow_the_limiter(api):
    limiter = ChatLimiter(per_user=1, total=100)
    api.client.app.state.chat_limiter = limiter
    for _ in range(5):
        assert api.client.post("/api/assistant/chat", json={"user_id": "f" * 24, "message": "hi"}).status_code == 404
    assert len(limiter._user) == 0
    user_id = create_user(api.client)
    assert api.client.post("/api/assistant/chat", json={"user_id": user_id, "message": "hi"}).status_code == 200
    assert api.client.post("/api/assistant/chat", json={"user_id": user_id, "message": "hi"}).status_code == 429


def test_global_cap_across_users(api):
    api.client.app.state.chat_limiter = ChatLimiter(per_user=10, total=2)
    users = [create_user(api.client) for _ in range(3)]
    assert [api.client.post("/api/assistant/chat", json={"user_id": u, "message": "hi"}).status_code
            for u in users] == [200, 200, 429]


def test_idle_keys_are_pruned():
    now = [0.0]
    limiter = SlidingWindowLimiter(5, window_s=60, clock=lambda: now[0])
    for i in range(1100):
        limiter.check(f"user-{i}")
    now[0] = 120
    limiter.check("late")
    assert len(limiter) == 1


# --- 8: only Gemini is probed ------------------------------------------------------------------

async def test_non_gemini_provider_is_reported_not_probed():
    s = Settings(_env_file=None, llm_provider="openai", llm_api_key="k", llm_model="m")
    h = await check_health(s, None, load_assumptions(), deep=False)
    assert h.dependencies["llm"].status == "not_configured" and "gemini" in h.dependencies["llm"].detail


# --- 9: database errors are classified -----------------------------------------------------------

@pytest.mark.parametrize("exc, status, code", [
    (ServerSelectionTimeoutError("down"), 503, "database_unavailable"),
    (DuplicateKeyError("dup"), 409, "conflict"),
    (OperationFailure("bad query"), 500, "database_error"),
])
def test_database_errors_are_classified(api, exc, status, code):
    api.client.app.dependency_overrides[get_store] = lambda: BrokenStore(exc)
    r = api.client.get("/api/users/" + "a" * 24)
    assert r.status_code == status and r.json()["error"]["code"] == code


async def test_weather_cache_write_race_is_retried():
    attempts = []

    class Collection:
        async def replace_one(self, *a, **k):
            attempts.append(1)
            if len(attempts) == 1:
                raise DuplicateKeyError("lost the race")

        async def find_one_and_replace(self, *a, **k):
            return {"_id": "x"}

    repo = MongoWeatherRepo({"weather_records": Collection(), "weather_forecasts": Collection()})
    await repo.save_current({"grid_key": "g"}, {})
    assert len(attempts) == 2
