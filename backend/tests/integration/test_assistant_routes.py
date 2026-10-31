from app.integrations.llm.base import LLMRateLimited, LLMUnavailable
from tests.fakes import FailingMemory
from tests.integration.journey import assess, create_property, create_user


def ready_user(api, **user_fields) -> str:
    """A homeowner who has finished the roof and estimate steps."""
    user_id = create_user(api.client, **user_fields)
    property_id = create_property(api.client, user_id)
    assessment_id = assess(api.client, user_id, property_id).json()["assessment_id"]
    r = api.client.post("/api/solar/estimate", json={"user_id": user_id, "assessment_id": assessment_id})
    assert r.status_code == 201, r.text
    return user_id


def chat(api, user_id, message, meko=True):
    r = api.client.post("/api/assistant/chat", json={"user_id": user_id, "message": message, "meko_enabled": meko})
    assert r.status_code == 200, r.text
    return r.json()


def test_memory_off_starts_fresh_and_asks_again(api):
    user_id = ready_user(api)
    body = chat(api, user_id, "Hi, where was I?", meko=False)
    assert "don't have your home's details" in body["reply"]
    assert body["memory"] == {"enabled": False, "live": False, "is_mock": True, "recalled": 0, "shared": 0,
                              "written": 0, "error": None}
    assert body["llm"]["fallback_reason"] == "no_facts"
    assert api.llm.prompts == []  # no quota spent when there is nothing to explain
    assert api.memory.rows == []


def test_memory_on_resumes_and_saves_summaries(api):
    user_id = ready_user(api)
    body = chat(api, user_id, "Hi, where was I?")
    assert body["agents"] == ["roof", "weather", "financial", "policy", "application"]
    assert all(o["status"] == "ok" for o in body["agent_outputs"])
    assert body["llm"]["used"] is True and body["llm"]["fallback_reason"] is None
    assert body["memory"]["written"] == 4  # the application agent saves once an application exists

    # Saved after the reply, one per agent, scoped to this user's conversation.
    saved = {hit.agent_id for _, hit in api.memory.rows}
    assert saved == {"aroha:roof", "aroha:weather", "aroha:financial", "aroha:policy"}
    assert api.store.data["users"][user_id]["meko_conversation_id"] == f"mock-conv-{user_id}"


def test_second_visit_recalls_and_does_not_duplicate(api):
    user_id = ready_user(api)
    chat(api, user_id, "Hi, where was I?")
    body = chat(api, user_id, "Hi again, where was I?")
    assert body["memory"]["recalled"] == 4
    assert body["memory"]["written"] == 0
    assert "What Aroha remembers" in api.llm.prompts[-1]
    assert len(api.memory.rows) == 4


def test_no_duplicates_even_when_recall_misses(api):
    # Live Meko drops weak matches, so a greeting can recall nothing; saves must still not repeat.
    user_id = ready_user(api)
    chat(api, user_id, "Hi, where was I?")
    assert len(api.store.data["users"][user_id]["meko_saved"]) == 4
    stored = list(api.memory.rows)
    api.memory.rows.clear()  # simulate a search that finds nothing
    body = chat(api, user_id, "Hello?")
    assert body["memory"]["recalled"] == 0 and body["memory"]["written"] == 0
    api.memory.rows.extend(stored)


def test_recall_query_adds_each_agents_topic(api):
    user_id = ready_user(api)
    seen = {}
    original = api.memory.session

    def spying_session():
        cm = original()

        class Wrap:
            async def __aenter__(self):
                s = await cm.__aenter__()
                real = s.search

                async def search(conv, queries, k=5):
                    seen.update(queries)
                    return await real(conv, queries, k)
                s.search = search
                return s

            async def __aexit__(self, *exc):
                return await cm.__aexit__(*exc)
        return Wrap()

    api.memory.session = spying_session
    chat(api, user_id, "Hi, where was I?")
    assert set(seen) == {"aroha:roof", "aroha:weather", "aroha:financial", "aroha:policy", "aroha:application"}
    assert "usable area" in seen["aroha:roof"] and "payback" in seen["aroha:financial"]


def test_question_routes_to_the_right_agent(api):
    user_id = ready_user(api)
    body = chat(api, user_id, "How much will I save, and what's the payback?")
    assert body["agents"] == ["financial"]
    facts = " ".join(body["agent_outputs"][0]["facts"])
    assert "₹" in facts and "payback" in facts and "not guarantees" in facts


def test_forecast_question_includes_the_outlook(api):
    user_id = ready_user(api)
    body = chat(api, user_id, "What does the weather look like this week?")
    facts = " ".join(body["agent_outputs"][0]["facts"])
    assert "Short-term outlook (not used in any estimate)" in facts


def test_invented_number_is_retried_then_replaced_by_the_template(api):
    user_id = ready_user(api)
    api.llm.replies = ["It costs about ₹99,999.", "Payback is 12 years."]
    body = chat(api, user_id, "What does it cost?")
    assert body["llm"]["fallback_reason"] == "invalid_numbers"
    assert "99,999" not in body["reply"] and "₹" in body["reply"]
    assert len(api.llm.prompts) == 2 and "previous draft" in api.llm.prompts[1]


def test_invented_number_fixed_on_retry(api):
    user_id = ready_user(api)
    api.llm.replies = ["About ₹99,999 a year."]  # then the default, valid reply
    body = chat(api, user_id, "What does it cost?")
    assert body["llm"]["fallback_reason"] is None and body["reply"].startswith("Here you go")


def test_rate_limit_falls_back_to_template(api):
    user_id = ready_user(api)
    api.llm.error = LLMRateLimited()
    body = chat(api, user_id, "How many panels fit?")
    assert body["llm"]["fallback_reason"] == "rate_limited"
    assert "panels" in body["reply"]


def test_llm_outage_falls_back_to_template(api):
    user_id = ready_user(api)
    api.llm.error = LLMUnavailable("down")
    assert chat(api, user_id, "How many panels fit?")["llm"]["fallback_reason"] == "unavailable"


def test_memory_outage_continues_fresh_and_says_so(api):
    user_id = ready_user(api)
    api.client.app.state.memory = FailingMemory()
    body = chat(api, user_id, "Hi, where was I?")
    assert body["memory"]["error"] and body["memory"]["live"] is False
    assert any("unavailable" in n for n in body["notes"])
    assert "don't have your home's details" in body["reply"]


def test_estimate_for_an_older_roof_is_flagged(api):
    user_id = ready_user(api)
    property_id = api.client.get(f"/api/users/{user_id}").json()["latest"]["property_id"]
    assess(api.client, user_id, property_id, shading={"south": "partial"})  # newer roof, no new estimate
    facts = " ".join(chat(api, user_id, "What will I save?")["agent_outputs"][0]["facts"])
    assert "earlier roof drawing" in facts


def test_run_is_logged_with_memory_calls(api):
    user_id = ready_user(api)
    body = chat(api, user_id, "Hi, where was I?")
    logs = [d for d in api.store.data["agent_logs"].values() if d["run_id"] == body["run_id"]]
    assert len(logs) == 1
    log = logs[0]
    assert log["agents"] == ["roof", "weather", "financial", "policy", "application"]
    assert sorted(c["tool"] for c in log["meko"]["calls"]) == [
        "mock.conversation_create", "mock.knowledgebase_search", "mock.memory_search"]
    assert [c["tool"] for c in log["meko_commit_calls"]] == ["mock.memory_add"] * 4
    assert log["llm"]["model"] == "fake-llm"


def test_memories_that_mention_the_name_are_not_saved(api):
    user_id = ready_user(api, display_name="panels")  # the roof summary mentions "panels"
    body = chat(api, user_id, "Hi, where was I?")
    assert body["memory"]["written"] == 3
    assert "aroha:roof" not in {hit.agent_id for _, hit in api.memory.rows}


def test_unknown_user_is_404(api):
    r = api.client.post("/api/assistant/chat", json={"user_id": "f" * 24, "message": "hi"})
    assert r.status_code == 404
