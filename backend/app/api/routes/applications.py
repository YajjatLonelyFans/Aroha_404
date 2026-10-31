from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_application_service
from app.schemas.application import ApplicationResponse, CreateApplicationRequest, UpdateApplicationRequest
from app.services.application_service import ApplicationService

router = APIRouter(prefix="/applications", tags=["applications"])
Service = Annotated[ApplicationService, Depends(get_application_service)]


@router.post("", response_model=ApplicationResponse, status_code=201)
async def create(body: CreateApplicationRequest, svc: Service) -> ApplicationResponse:
    """Start tracking: steps and document checklist from the stored procedure for the user's DISCOM."""
    return await svc.create(body)


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get(application_id: str, svc: Service, user_id: Annotated[str, Query()]) -> ApplicationResponse:
    return await svc.get(application_id, user_id)


@router.patch("/{application_id}", response_model=ApplicationResponse)
async def update(application_id: str, body: UpdateApplicationRequest, svc: Service) -> ApplicationResponse:
    """Mark a step's status or a document as provided."""
    return await svc.update(application_id, body)
