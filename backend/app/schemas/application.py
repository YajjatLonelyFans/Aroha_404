from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

StepStatus = Literal["todo", "doing", "done"]
AppStatus = Literal["planning", "applied", "inspection", "commissioned"]


class CreateApplicationRequest(BaseModel):
    user_id: str


class StepOut(BaseModel):
    id: str
    title: str
    stage: AppStatus
    actor: str
    status: StepStatus
    updated_at: datetime | None


class DocumentOut(BaseModel):
    type: str
    label: str
    required: bool
    provided: bool
    verified: bool  # whether this requirement was confirmed on an official page
    source_url: str


class ApplicationResponse(BaseModel):
    application_id: str
    user_id: str
    discom: str
    status: AppStatus
    steps: list[StepOut]
    documents: list[DocumentOut]
    next_actions: list[str]
    missing_documents: list[str]
    source_url: str
    verified_on: str
    note: str


class UpdateApplicationRequest(BaseModel):
    user_id: str
    step_id: str | None = None
    step_status: StepStatus | None = None
    document_type: str | None = None
    provided: bool | None = None

    @model_validator(mode="after")
    def _check(self) -> "UpdateApplicationRequest":
        step = self.step_id is not None and self.step_status is not None
        doc = self.document_type is not None and self.provided is not None
        if not (step or doc):
            raise ValueError("Send step_id with step_status, or document_type with provided.")
        return self
