from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Source


class SolarEstimateRequest(BaseModel):
    user_id: str
    assessment_id: str
    capacities_kwp: list[float] | None = Field(
        None, max_length=3, description="Optional; default is the recommended size and its neighbours"
    )
    monthly_units_kwh: float | None = Field(None, gt=0, le=20000, description="Optional; default from the user")


class Band(BaseModel):
    p10: float | None
    median: float | None
    p90: float | None


class MonthKwh(Band):
    month: int


class Range(BaseModel):
    low: float | None
    likely: float | None
    high: float | None


class SubsidyLine(BaseModel):
    scheme_id: str
    name: str
    amount_inr: float


class EstimateOption(BaseModel):
    capacity_kwp: float
    panel_count: int
    recommended: bool
    monthly_kwh: list[MonthKwh]
    annual_kwh: Band
    gross_cost_inr: float | None
    subsidy_inr: float
    subsidy_breakdown: list[SubsidyLine]
    net_cost_inr: float | None
    annual_savings_inr: Range
    payback_years: Range
    # Generation-based incentive, paid per unit generated for a limited number of years.
    annual_incentive_inr: Range | None
    incentive_years: int | None
    payback_years_with_incentive: Range | None
    missing: list[str]


class SolarEstimateResponse(BaseModel):
    estimate_id: str
    assessment_id: str
    climatology_id: str
    monthly_units_kwh: float
    options: list[EstimateOption]
    recommended_kwp: float
    binding_constraint: Literal["roof", "consumption", "limit", "minimum"]
    roof_kwp: float
    consumption_kwp: float
    shading_loss_fraction: float
    assumptions: list[str]
    notes: list[str]
    disclaimer: str
    assumptions_version: str
    model_version: str
    sources: list[Source]
    is_mock: bool
