"""Qualifying answers, the user profile and the property pin."""

from collections.abc import Callable
from datetime import datetime

from app.core.assumptions import Assumptions
from app.core.errors import AppError, NotFoundError
from app.db import collections as c
from app.db.store import DocumentStore
from app.domain.geometry import check_point_in_bbox
from app.schemas.user import (
    CreatePropertyRequest,
    CreatePropertyResponse,
    CreateUserRequest,
    PropertyOut,
    SavedRoof,
    CreateUserResponse,
    LatestIds,
    UserSummary,
)
from app.services.weather_service import grid_key, utc_now

NO_ROOF_RIGHTS = (
    "Rooftop solar needs the right to use the roof. Builder-floor roofs are often shared: "
    "get written permission from the owner or the other residents, then start again."
)
OUT_OF_SCOPE_PROPERTY = "Aroha covers independent houses and builder floors in Delhi for now."


def qualify(req: CreateUserRequest) -> tuple[bool, str | None]:
    if not req.has_roof_rights:
        return False, NO_ROOF_RIGHTS
    if req.property_type == "other":
        return False, OUT_OF_SCOPE_PROPERTY
    return True, None


class UserService:
    def __init__(
        self,
        store: DocumentStore,
        assumptions: Assumptions,
        meko_enabled_default: bool,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._store = store
        self._a = assumptions
        self._meko_default = meko_enabled_default
        self._clock = clock

    async def create_user(self, req: CreateUserRequest) -> CreateUserResponse:
        eligible, reason = qualify(req)
        now = self._clock()
        user_id = await self._store.insert(c.USERS, {
            **req.model_dump(),
            "eligible_to_continue": eligible,
            "reason": reason,
            "prefs": {"language": "en"},
            "meko_enabled": self._meko_default,
            "created_at": now,
            "updated_at": now,
        })
        return CreateUserResponse(user_id=user_id, eligible_to_continue=eligible, reason=reason)

    async def require_user(self, user_id: str) -> dict:
        user = await self._store.get(c.USERS, user_id)
        if user is None:
            raise NotFoundError("User")
        return user

    async def summary(self, user_id: str) -> UserSummary:
        user = await self.require_user(user_id)
        latest = {}
        for field, collection in (
            ("property_id", c.PROPERTIES),
            ("assessment_id", c.ROOF_ASSESSMENTS),
            ("estimate_id", c.SOLAR_ESTIMATES),
            ("application_id", c.APPLICATIONS),
        ):
            doc = await self._store.latest(collection, {"user_id": user_id})
            latest[field] = doc["id"] if doc else None
        return UserSummary(
            user_id=user["id"],
            display_name=user.get("display_name"),
            property_type=user["property_type"],
            has_roof_rights=user["has_roof_rights"],
            monthly_units_kwh=user["monthly_units_kwh"],
            discom=user["discom"],
            eligible_to_continue=user["eligible_to_continue"],
            reason=user.get("reason"),
            meko_enabled=user.get("meko_enabled", self._meko_default),
            created_at=user["created_at"],
            latest=LatestIds(**latest),
        )

    async def create_property(self, req: CreatePropertyRequest) -> CreatePropertyResponse:
        user = await self.require_user(req.user_id)
        if not user["eligible_to_continue"]:
            raise AppError("not_eligible", user.get("reason") or "This journey cannot continue.", status_code=409)
        check_point_in_bbox(req.lat, req.lon, self._a.validation.delhi_bbox)

        _, _, gk = grid_key(req.lat, req.lon)
        now = self._clock()
        property_id = await self._store.insert(c.PROPERTIES, {
            "user_id": req.user_id,
            "pin": {"type": "Point", "coordinates": [req.lon, req.lat]},
            "grid_key": gk,
            "address_text": req.address_text,
            "created_at": now,
            "updated_at": now,
        })
        return CreatePropertyResponse(property_id=property_id, grid_key=gk, lat=req.lat, lon=req.lon)

    async def get_property(self, property_id: str) -> PropertyOut:
        doc = await self._store.get(c.PROPERTIES, property_id)
        if doc is None:
            raise NotFoundError("Property")
        lon, lat = doc["pin"]["coordinates"]
        return PropertyOut(
            property_id=doc["id"],
            user_id=doc["user_id"],
            lat=lat,
            lon=lon,
            grid_key=doc["grid_key"],
            address_text=doc.get("address_text"),
            created_at=doc["created_at"],
            roof=SavedRoof(**{k: doc.get(k) for k in SavedRoof.model_fields if doc.get(k) is not None})
            if doc.get("roof_type") else None,
        )
