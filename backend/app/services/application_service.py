"""Application tracker built from the stored, sourced procedure for the homeowner's DISCOM.

Progress is what the homeowner marks. Aroha never marks a step done itself and
never reports an approval it has not been told about.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.core.errors import AppError, NotFoundError
from app.db import collections as c
from app.db.store import DocumentStore
from app.schemas.application import (
    ApplicationResponse,
    CreateApplicationRequest,
    DocumentOut,
    StepOut,
    UpdateApplicationRequest,
)
from app.services.weather_service import utc_now

STAGES = ("planning", "applied", "inspection", "commissioned")
NOTE = "Progress shows what you have marked. Approvals come only from your DISCOM and the national portal."


def overall_status(steps: list[dict[str, Any]]) -> str:
    """The stage of the furthest step marked done, or planning if none."""
    done = [s["stage"] for s in steps if s["status"] == "done"]
    return max(done, key=STAGES.index) if done else "planning"


def to_response(app_id: str, doc: dict[str, Any]) -> ApplicationResponse:
    steps = doc["steps"]
    todo = [s for s in steps if s["status"] != "done"]
    missing = [d["label"] for d in doc["documents"] if d["required"] and not d["provided"]]
    return ApplicationResponse(
        application_id=app_id,
        user_id=doc["user_id"],
        discom=doc["discom"],
        status=doc["status"],
        steps=[StepOut(**s) for s in steps],
        documents=[DocumentOut(**d) for d in doc["documents"]],
        next_actions=[s["title"] for s in todo[:2]],
        missing_documents=missing,
        source_url=doc["source_url"],
        verified_on=doc["verified_on"],
        note=NOTE,
    )


class ApplicationService:
    def __init__(self, store: DocumentStore, clock: Callable[[], datetime] = utc_now) -> None:
        self._store = store
        self._clock = clock

    async def procedure_for(self, discom: str) -> dict[str, Any] | None:
        for p in await self._store.find(c.PROCEDURES, {}):
            if discom in p["discoms"]:
                return p
        return None

    async def create(self, req: CreateApplicationRequest) -> ApplicationResponse:
        user = await self._store.get(c.USERS, req.user_id)
        if user is None:
            raise NotFoundError("User")
        if not user["eligible_to_continue"]:
            raise AppError("not_eligible", user.get("reason") or "This journey cannot continue.", status_code=409)
        procedure = await self.procedure_for(user["discom"])
        if procedure is None:
            raise AppError("no_procedure", f"No verified procedure is stored for {user['discom']} yet.",
                           status_code=422)
        prop = await self._store.latest(c.PROPERTIES, {"user_id": req.user_id})
        now = self._clock()
        doc = {
            "user_id": req.user_id,
            "property_id": prop["id"] if prop else None,
            "discom": user["discom"],
            "procedure_id": procedure["procedure_id"],
            "source_url": procedure["source_url"],
            "verified_on": procedure["verified_on"],
            "status": "planning",
            "steps": [{**{k: s[k] for k in ("id", "title", "stage", "actor")}, "status": "todo", "updated_at": None}
                      for s in procedure["steps"]],
            "documents": [{**{k: d[k] for k in ("type", "label", "required", "verified", "source_url")},
                           "provided": False} for d in procedure["documents"]],
            "created_at": now,
            "updated_at": now,
        }
        app_id = await self._store.insert(c.APPLICATIONS, doc)
        return to_response(app_id, doc)

    async def _own(self, app_id: str, user_id: str) -> dict[str, Any]:
        doc = await self._store.get(c.APPLICATIONS, app_id)
        if doc is None or doc["user_id"] != user_id:
            raise NotFoundError("Application")
        return doc

    async def get(self, app_id: str, user_id: str) -> ApplicationResponse:
        return to_response(app_id, await self._own(app_id, user_id))

    async def update(self, app_id: str, req: UpdateApplicationRequest) -> ApplicationResponse:
        doc = await self._own(app_id, req.user_id)
        now = self._clock()
        if req.step_id is not None:
            step = next((s for s in doc["steps"] if s["id"] == req.step_id), None)
            if step is None:
                raise AppError("unknown_step", f"No step called '{req.step_id}'.", status_code=422)
            step["status"], step["updated_at"] = req.step_status, now
        if req.document_type is not None:
            item = next((d for d in doc["documents"] if d["type"] == req.document_type), None)
            if item is None:
                raise AppError("unknown_document", f"No document called '{req.document_type}'.", status_code=422)
            item["provided"] = req.provided
        doc["status"] = overall_status(doc["steps"])
        await self._store.update(c.APPLICATIONS, app_id, {
            "steps": doc["steps"], "documents": doc["documents"], "status": doc["status"], "updated_at": now,
        })
        return to_response(app_id, doc)
