"""Load the team-curated policy and procedure records from backend/seed/ into MongoDB.

Runs at startup. Records are validated strictly and replaced by id, so editing a
JSON file and restarting is how a record is corrected or re-verified.
"""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.core.settings import BACKEND_DIR
from app.db import collections as c
from app.schemas.policy import PolicyRecord

log = logging.getLogger(__name__)

SEED_DIR = BACKEND_DIR / "seed"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcedureStep(_Strict):
    id: str
    stage: str
    actor: str
    title: str


class ProcedureDocument(_Strict):
    type: str
    label: str
    required: bool
    verified: bool
    source_url: str


class Lesson(_Strict):
    text: str
    source_url: str
    verified_on: str


class Procedure(_Strict):
    procedure_id: str
    name: str
    discoms: list[str]
    source_url: str
    verified_on: str
    verified_by: str
    steps: list[ProcedureStep]
    documents: list[ProcedureDocument]
    lessons: list[Lesson] = Field(default_factory=list)


def load_policy_records(path: Path = SEED_DIR / "policy_records.json") -> list[PolicyRecord]:
    return [PolicyRecord.model_validate(r) for r in json.loads(path.read_text(encoding="utf-8"))]


def load_procedures(path: Path = SEED_DIR / "procedures.json") -> list[Procedure]:
    return [Procedure.model_validate(p) for p in json.loads(path.read_text(encoding="utf-8"))]


def policy_doc(record: PolicyRecord) -> dict[str, Any]:
    return record.model_dump(mode="json")


async def seed_database(db: AsyncDatabase) -> None:
    records = load_policy_records()
    for r in records:
        await db[c.POLICY_RECORDS].replace_one({"scheme_id": r.scheme_id}, policy_doc(r), upsert=True)
    procedures = load_procedures()
    for p in procedures:
        await db[c.PROCEDURES].replace_one({"procedure_id": p.procedure_id}, p.model_dump(), upsert=True)
    log.info("Seeded %d policy records and %d procedures", len(records), len(procedures))
