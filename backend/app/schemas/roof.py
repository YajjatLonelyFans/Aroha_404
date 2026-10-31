from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Confidence

ShadeLevel = Literal["none", "partial", "heavy"]
NoGoKind = Literal["water_tank", "stair_room", "solar_heater", "other"]


class Shading(BaseModel):
    """Shade from taller buildings or trees, by the side it comes from."""

    east: ShadeLevel = "none"
    south: ShadeLevel = "none"
    west: ShadeLevel = "none"
    north: ShadeLevel = "none"


class NoGoArea(BaseModel):
    kind: NoGoKind
    geometry: dict[str, Any] = Field(description="GeoJSON Polygon (WGS84)")


class ManualDimensions(BaseModel):
    """Fallback when the map cannot be used: a rectangle plus no-go areas by size."""

    length_m: float = Field(gt=0, le=200)
    width_m: float = Field(gt=0, le=200)
    no_go_areas_m2: list[float] = Field(default_factory=list)


class RoofAssessRequest(BaseModel):
    user_id: str
    property_id: str
    outline: dict[str, Any] | None = Field(None, description="GeoJSON Polygon (WGS84)")
    no_go_areas: list[NoGoArea] = Field(default_factory=list)
    roof_type: Literal["flat", "sloped"]
    slope_azimuth_deg: float | None = Field(None, ge=-180, le=180, description="Sloped only; 0 = south")
    slope_tilt_deg: float | None = Field(None, ge=0, lt=90, description="Sloped only")
    shading: Shading = Field(default_factory=Shading)
    manual_dimensions: ManualDimensions | None = None

    @model_validator(mode="after")
    def _check(self) -> "RoofAssessRequest":
        if (self.outline is None) == (self.manual_dimensions is None):
            raise ValueError("Send either an outline or manual_dimensions, not both.")
        if self.manual_dimensions is not None and self.no_go_areas:
            raise ValueError("With manual_dimensions, give no-go areas as manual_dimensions.no_go_areas_m2.")
        if self.roof_type == "sloped" and (self.slope_azimuth_deg is None or self.slope_tilt_deg is None):
            raise ValueError("A sloped roof needs slope_azimuth_deg and slope_tilt_deg.")
        return self


class ConstraintOut(BaseModel):
    code: str
    message: str


class KwpRange(BaseModel):
    min: float
    likely: float
    max: float


class RoofAssessResponse(BaseModel):
    assessment_id: str
    property_id: str
    outline_area_m2: float
    setback_area_m2: float
    no_go_area_m2: float
    usable_area_m2: float
    panel_layout: dict[str, Any] | None = Field(description="GeoJSON FeatureCollection; null for manual dimensions")
    panel_count: int
    module_wp: float
    capacity_kwp: KwpRange
    array_tilt_deg: float
    array_azimuth_deg: float
    orientation: Literal["portrait", "landscape"] | None
    row_gap_m: float | None
    shading_loss_fraction: float
    constraints: list[ConstraintOut]
    assumptions: list[str]
    confidence: Confidence
    traced: bool
    assumptions_version: str
    model_version: str
