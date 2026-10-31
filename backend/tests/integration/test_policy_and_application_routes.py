import pytest

from app.db.seed import Lesson
from app.integrations.meko.base import MemoryHit
from app.integrations.meko.mock import MockMemoryProvider
from app.services.knowledge_service import promote_lessons
from tests.integration.journey import create_user
from tests.integration.test_assistant_routes import chat, ready_user


def _schemes(body):
    return {s["scheme_id"]: s for s in body["schemes"]}


# --- eligibility --------------------------------------------------------------------------

def test_eligibility_after_an_estimate(api):
    user_id = ready_user(api)
    body = api.client.post("/api/policy/eligibility", json={"user_id": user_id}).json()
    s = _schemes(body)
    kwp = body["capacity_kwp"]
    assert s["pm-surya-ghar-cfa"]["eligible"] == "yes" and s["pm-surya-ghar-cfa"]["amount_inr"] > 0
    assert s["delhi-capital-subsidy"]["amount_inr"] == min(2000 * kwp, 10000)
    assert s["delhi-gbi"]["inr_per_kwh"] in (2, 3) and s["delhi-gbi"]["incentive_years"] == 5
    zero = s["delhi-zero-upfront-3kw-2026"]
    assert zero["eligible"] == "unknown" and zero["counts_in_estimate"] is False
    assert body["total_subsidy_inr"] == s["pm-surya-ghar-cfa"]["amount_inr"] + s["delhi-capital-subsidy"]["amount_inr"]
    assert all(x["source_url"].startswith("https://") and x["verified_on"] for x in body["schemes"])
    assert "does not apply on your behalf" in body["disclaimer"]


def test_eligibility_before_any_estimate_has_no_amounts(api):
    user_id = create_user(api.client)
    body = api.client.post("/api/policy/eligibility", json={"user_id": user_id}).json()
    assert body["capacity_kwp"] is None and body["total_subsidy_inr"] == 0
    assert _schemes(body)["delhi-gbi"]["eligible"] == "unknown"
    assert any("get an estimate first" in n for n in body["notes"])


def test_eligibility_for_a_chosen_size(api):
    user_id = create_user(api.client)
    body = api.client.post("/api/policy/eligibility", json={"user_id": user_id, "capacity_kwp": 5}).json()
    s = _schemes(body)
    assert s["pm-surya-ghar-cfa"]["amount_inr"] == 78000 and s["delhi-capital-subsidy"]["amount_inr"] == 10000
    assert s["delhi-gbi"]["inr_per_kwh"] == 2


def test_no_roof_rights_is_not_eligible(api):
    user_id = create_user(api.client, has_roof_rights=False)
    body = api.client.post("/api/policy/eligibility", json={"user_id": user_id, "capacity_kwp": 3}).json()
    assert all(s["eligible"] in ("no", "unknown") for s in body["schemes"])
    assert body["total_subsidy_inr"] == 0


# --- applications -------------------------------------------------------------------------

def _create(api, user_id):
    r = api.client.post("/api/applications", json={"user_id": user_id})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_application_from_the_official_procedure(api):
    user_id = create_user(api.client)
    app = _create(api, user_id)
    assert app["status"] == "planning" and len(app["steps"]) == 10 and len(app["documents"]) == 5
    assert all(s["status"] == "todo" for s in app["steps"])
    assert app["next_actions"][0].startswith("Register on the national rooftop solar portal")
    assert len(app["missing_documents"]) == 4
    assert app["source_url"] == "https://eerem.delhi.gov.in/hi/node/12632"
    assert "Approvals come only from your DISCOM" in app["note"]


def test_progress_updates(api):
    user_id = create_user(api.client)
    app_id = _create(api, user_id)["application_id"]
    url = f"/api/applications/{app_id}"
    for step in ("register", "apply"):
        r = api.client.patch(url, json={"user_id": user_id, "step_id": step, "step_status": "done"})
    body = r.json()
    assert body["status"] == "applied"
    assert body["next_actions"][0].startswith("The DISCOM checks technical feasibility")
    body = api.client.patch(url, json={"user_id": user_id, "document_type": "bank_details", "provided": True}).json()
    assert "Bank account details and a cancelled cheque" not in body["missing_documents"]
    again = api.client.get(url, params={"user_id": user_id}).json()
    assert again["status"] == "applied" and len(again["missing_documents"]) == 3


@pytest.mark.parametrize("patch, code", [
    ({"step_id": "teleport", "step_status": "done"}, 422),
    ({"document_type": "passport", "provided": True}, 422),
    ({}, 422),
])
def test_bad_updates(api, patch, code):
    user_id = create_user(api.client)
    app_id = _create(api, user_id)["application_id"]
    r = api.client.patch(f"/api/applications/{app_id}", json={"user_id": user_id, **patch})
    assert r.status_code == code


def test_someone_elses_application_is_404(api):
    app_id = _create(api, create_user(api.client))["application_id"]
    other = create_user(api.client)
    assert api.client.get(f"/api/applications/{app_id}", params={"user_id": other}).status_code == 404


def test_ineligible_user_cannot_start_an_application(api):
    user_id = create_user(api.client, has_roof_rights=False)
    assert api.client.post("/api/applications", json={"user_id": user_id}).status_code == 409


def test_summary_includes_the_application(api):
    user_id = create_user(api.client)
    app_id = _create(api, user_id)["application_id"]
    assert api.client.get(f"/api/users/{user_id}").json()["latest"]["application_id"] == app_id


# --- chat with policy, application and shared lessons ------------------------------------------

LESSON = ("Delhi rooftop solar: the state capital subsidy and the generation-based incentive are paid by the "
          "DISCOM against the first electricity bill after the net meter is installed.")


def test_subsidy_question_cites_sources(api):
    user_id = ready_user(api)
    body = chat(api, user_id, "Am I eligible for the subsidy?")
    policy = next(o for o in body["agent_outputs"] if o["agent"] == "policy")
    facts = " ".join(policy["facts"])
    assert "you appear eligible" in facts and "Source checked on 01 Nov 2026" in facts
    assert "needs verification" in facts


def test_shared_lesson_reaches_another_homeowner(api):
    api.memory.shared.append(MemoryHit("kb-1", LESSON, "aroha:application", {"source": "memory"}))
    user_id = ready_user(api)  # a different homeowner from whoever produced the lesson
    body = chat(api, user_id, "What are the next steps to apply?")
    assert body["agents"] == ["application"] and body["memory"]["shared"] == 1
    facts = " ".join(body["agent_outputs"][0]["facts"])
    assert "Verified tip shared by Aroha" in facts and "first electricity bill" in facts


def test_shared_lessons_are_not_used_with_memory_off(api):
    api.memory.shared.append(MemoryHit("kb-1", LESSON, "aroha:application", {}))
    body = chat(api, ready_user(api), "What are the next steps to apply?", meko=False)
    assert body["memory"]["shared"] == 0
    assert "Verified tip" not in body["reply"]


def test_application_progress_in_chat_and_memory(api):
    user_id = ready_user(api)
    app_id = _create(api, user_id)["application_id"]
    api.client.patch(f"/api/applications/{app_id}", json={"user_id": user_id, "step_id": "register", "step_status": "done"})
    body = chat(api, user_id, "Which documents do I still need?")
    facts = " ".join(body["agent_outputs"][0]["facts"])
    assert "1 of 10 steps marked done" in facts and "Documents still needed" in facts
    assert body["memory"]["written"] == 1


# --- promoting lessons ------------------------------------------------------------------------

async def test_promote_lessons_once_and_reject_unsafe_ones():
    memory = MockMemoryProvider()
    good = Lesson(text=LESSON, source_url="https://eerem.delhi.gov.in/hi/node/12632", verified_on="2026-11-01")
    unsafe = Lesson(text="Call 9876543210 for a faster approval.", source_url="https://x.example", verified_on="2026-11-01")
    first = await promote_lessons(memory, [good, unsafe])
    assert first.promoted == [LESSON]
    assert first.rejected and "phone" in first.rejected[0][1]
    assert [h.text for h in memory.shared] == [LESSON] and memory.rows == []

    second = await promote_lessons(memory, [good])
    assert second.promoted == [] and second.already_shared == [LESSON]
    assert len(memory.shared) == 1
