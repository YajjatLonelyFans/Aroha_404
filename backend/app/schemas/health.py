from typing import Literal

from pydantic import BaseModel

# ok: checked and working · error: checked and failing
# configured: settings present but not checked · not_configured: settings missing
DependencyState = Literal["ok", "error", "configured", "not_configured"]


class DependencyStatus(BaseModel):
    status: DependencyState
    detail: str | None = None
    is_mock: bool = False


class AssumptionsStatus(BaseModel):
    version: str
    complete: bool
    missing: list[str]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    app_env: str
    dependencies: dict[str, DependencyStatus]
    assumptions: AssumptionsStatus
