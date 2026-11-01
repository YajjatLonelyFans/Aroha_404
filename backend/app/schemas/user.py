from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.roof import ManualDimensions, NoGoArea, Shading

PropertyType = Literal["independent_house", "builder_floor", "other"]
Discom = Literal["BRPL", "BYPL", "TPDDL", "NDMC", "other"]


class CreateUserRequest(BaseModel):
    display_name: str | None = Field(None, max_length=80)
    property_type: PropertyType
    has_roof_rights: bool
    monthly_units_kwh: float = Field(gt=0, le=20000, description="Typical monthly use from the bill")
    discom: Discom


class CreateUserResponse(BaseModel):
    user_id: str
    eligible_to_continue: bool
    reason: str | None


class LatestIds(BaseModel):
    property_id: str | None = None
    assessment_id: str | None = None
    estimate_id: str | None = None
    application_id: str | None = None


class UserSummary(BaseModel):
    user_id: str
    display_name: str | None
    property_type: PropertyType
    has_roof_rights: bool
    monthly_units_kwh: float
    discom: Discom
    eligible_to_continue: bool
    reason: str | None
    meko_enabled: bool
    created_at: datetime
    latest: LatestIds


class CreatePropertyRequest(BaseModel):
    user_id: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    address_text: str | None = Field(None, max_length=300)


class SavedRoof(BaseModel):
    """What the homeowner last drew and answered, so the map can show it again."""

    outline: dict | None = Field(None, description="GeoJSON Polygon (WGS84)")
    no_go_areas: list[NoGoArea] = Field(default_factory=list)
    manual_dimensions: ManualDimensions | None = None
    roof_type: Literal["flat", "sloped"]
    slope_tilt_deg: float | None = None
    slope_azimuth_deg: float | None = None
    shading: Shading = Field(default_factory=Shading)


class PropertyOut(BaseModel):
    property_id: str
    user_id: str
    lat: float
    lon: float
    grid_key: str
    address_text: str | None
    created_at: datetime
    roof: SavedRoof | None = Field(None, description="Null until a roof has been assessed for this pin")


class CreatePropertyResponse(BaseModel):
    property_id: str
    grid_key: str
    lat: float
    lon: float
