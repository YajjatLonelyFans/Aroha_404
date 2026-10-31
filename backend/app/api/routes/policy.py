from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_policy_service
from app.schemas.policy import EligibilityRequest, EligibilityResponse
from app.services.policy_service import PolicyService

router = APIRouter(prefix="/policy", tags=["policy"])


@router.post("/eligibility", response_model=EligibilityResponse)
async def eligibility(
    body: EligibilityRequest, svc: Annotated[PolicyService, Depends(get_policy_service)]
) -> EligibilityResponse:
    """Each scheme as yes / no / unknown with reasons, source link and verified-on date.
    Only verified, current schemes count towards the subsidy total."""
    return await svc.eligibility(body)
