"""Types shared by API responses, agents and DB documents."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Confidence = Literal["low", "medium", "high"]


class Source(BaseModel):
    name: str
    url: str | None = None
    retrieved_at: datetime
    note: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ErrorResponse(BaseModel):
    error: ErrorDetail
