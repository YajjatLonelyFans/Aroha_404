from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Source


class PercentilesOut(BaseModel):
    p10: float | None
    median: float | None
    p90: float | None


class ClimatologyMonth(BaseModel):
    month: int
    gti_kwh_m2: PercentilesOut
    temp_mean_c: float | None
    cloud_cover_pct: float | None
    precip_mm: float | None
    sunshine_h: float | None
    missing_hours: int


class SeasonNoteOut(BaseModel):
    season: str
    statement: str
    evidence_fields: list[str]
    values: dict[str, float]


class SpecificYieldOut(BaseModel):
    """Energy per kWp before roof shading; any capacity's energy is kWp × this."""

    monthly_kwh_per_kwp: list[PercentilesOut]
    annual_kwh_per_kwp: PercentilesOut
    years_used: int
    low_confidence_months: list[int]


class MissingData(BaseModel):
    fields: list[str]
    hours: int
    excluded_months: list[tuple[int, int]]  # (year, month)


class ClimatologyResponse(BaseModel):
    climatology_id: str
    grid_key: str
    lat: float
    lon: float
    tilt_deg: float
    azimuth_deg: float
    period: str
    years: list[int]
    monthly: list[ClimatologyMonth]
    season_notes: list[SeasonNoteOut]
    specific_yield: SpecificYieldOut | None
    units: dict[str, str]
    assumptions: list[str]
    notes: list[str]
    missing: MissingData
    sources: list[Source]
    retrieved_at: datetime
    cached: bool
    is_mock: bool


class CurrentObservation(BaseModel):
    time: str  # local time reported by the provider
    temperature_c: float | None
    relative_humidity_pct: float | None
    precipitation_mm: float | None
    cloud_cover_pct: float | None
    wind_speed_kmh: float | None
    is_day: bool | None


class CurrentResponse(BaseModel):
    grid_key: str
    observation: CurrentObservation
    sources: list[Source]
    retrieved_at: datetime
    cached: bool
    is_mock: bool


class ForecastDayOut(BaseModel):
    date: str
    gti_kwh_m2: float | None
    cloud_cover_pct: float | None
    precip_mm: float | None
    temp_max_c: float | None
    temp_min_c: float | None
    outlook: Literal["sunny", "mixed", "cloudy", "rain"] | None


class ForecastResponse(BaseModel):
    label: Literal["Short-term outlook"] = "Short-term outlook"
    grid_key: str
    tilt_deg: float
    azimuth_deg: float
    horizon_days: int
    daily: list[ForecastDayOut]
    notes: list[str]
    sources: list[Source]
    retrieved_at: datetime
    cached: bool
    is_mock: bool
