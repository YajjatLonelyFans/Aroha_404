"""The agent log: each turn's timings and every Meko call, in the reply and from /assistant/logs."""

from tests.integration.journey import create_user
from tests.integration.test_assistant_routes import chat, ready_user


def test_reply_carries_memory_calls_and_timings(api):
    user_id = ready_user(api)
    body = chat(api, user_id, "How many panels fit?")
    assert body["memory"]["calls"], "recall calls are listed"
    assert all({"tool", "latency_ms", "ok"} <= set(call) for call in body["memory"]["calls"])
    assert {"records_ms", "recall_ms", "agents_ms", "compose_ms"} <= set(body["timings"])
    assert body["latency_ms"] >= 0


def test_logs_list_turns_newest_first_with_saves(api):
    user_id = ready_user(api)
    first = chat(api, user_id, "How many panels fit?")
    second = chat(api, user_id, "What will it cost?")
    r = api.client.get(f"/api/assistant/logs?user_id={user_id}")
    assert r.status_code == 200, r.text
    logs = r.json()["logs"]
    assert [log["run_id"] for log in logs[:2]] == [second["run_id"], first["run_id"]]
    newest = logs[0]
    assert newest["memory"]["enabled"] is True and newest["memory"]["calls"]
    # The test client runs the after-reply save before returning, so its calls are logged.
    assert newest["memory"]["commit_calls"] and all(c["ok"] for c in newest["memory"]["commit_calls"])
    assert newest["llm"]["used"] in (True, False) and newest["timings"]


def test_memory_off_makes_no_memory_calls(api):
    user_id = ready_user(api)
    body = api.client.post("/api/assistant/chat", json={"user_id": user_id, "message": "How many panels fit?",
                                                         "meko_enabled": False}).json()
    assert body["memory"]["enabled"] is False and body["memory"]["calls"] == []
    log = api.client.get(f"/api/assistant/logs?user_id={user_id}").json()["logs"][0]
    assert log["memory"]["calls"] == [] and log["memory"]["commit_calls"] is None


def test_logs_limit_and_unknown_user(api):
    user_id = ready_user(api)
    for _ in range(3):
        chat(api, user_id, "How many panels fit?")
    assert len(api.client.get(f"/api/assistant/logs?user_id={user_id}&limit=2").json()["logs"]) == 2
    assert api.client.get("/api/assistant/logs?user_id=" + "d" * 24).status_code == 404


def test_logs_only_show_that_users_turns(api):
    a, b = ready_user(api), create_user(api.client)
    chat(api, a, "How many panels fit?")
    assert api.client.get(f"/api/assistant/logs?user_id={b}").json()["logs"] == []
