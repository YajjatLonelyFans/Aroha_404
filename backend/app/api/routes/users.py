from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_user_service
from app.schemas.user import (
    CreatePropertyRequest,
    CreatePropertyResponse,
    CreateUserRequest,
    CreateUserResponse,
    UserSummary,
)
from app.services.user_service import UserService

router = APIRouter(tags=["users"])
Service = Annotated[UserService, Depends(get_user_service)]


@router.post("/users", response_model=CreateUserResponse, status_code=201)
async def create_user(body: CreateUserRequest, svc: Service) -> CreateUserResponse:
    """Qualifying answers. No roof rights (or an out-of-scope property) ends the journey with a reason."""
    return await svc.create_user(body)


@router.get("/users/{user_id}", response_model=UserSummary)
async def get_user(user_id: str, svc: Service) -> UserSummary:
    """Profile plus the latest property, assessment and estimate ids, for resuming a journey."""
    return await svc.summary(user_id)


@router.post("/properties", response_model=CreatePropertyResponse, status_code=201)
async def create_property(body: CreatePropertyRequest, svc: Service) -> CreatePropertyResponse:
    """Save the map pin for the house."""
    return await svc.create_property(body)
