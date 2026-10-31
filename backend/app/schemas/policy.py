from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Eligible = Literal["yes", "no", "unknown"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AmountTier(_Strict):
    up_to_kwp: float
    inr_per_kwp: float | None = None
    inr_per_kwh: float | None = None


class AmountRule(_Strict):
    type: Literal["tiered_per_kwp", "per_kwp", "gbi", "none"]
    tiers: list[AmountTier] = Field(default_factory=list)
    inr_per_kwp: float | None = None
    cap_inr: float | None = None
    years: int | None = None


class PolicyRules(_Strict):
    eligible_property_types: list[str]
    requires_roof_rights: bool
    discoms: list[str] | None = None
    capacity_kwp_max: float | None = None
    max_monthly_units_kwh: float | None = None
    conditions: list[str] = Field(default_factory=list)  # the homeowner must confirm these


class PolicyRecord(_Strict):
    """A scheme as stored in policy_records. Amounts live only here."""

    scheme_id: str
    name: str
    jurisdiction: Literal["central", "delhi"]
    kind: Literal["capital_subsidy", "generation_incentive", "programme"]
    summary: str
    rules: PolicyRules
    amount_rule: AmountRule
    source_url: str
    published_on: date | None = None
    effective_from: date | None = None
    verified_on: date
    verified_by: str
    status: Literal["verified", "unverified", "expired"]
    review_by: date | None = None
    notes: str | None = None


class EligibilityRequest(BaseModel):
    user_id: str
    capacity_kwp: float | None = Field(None, gt=0, le=100, description="Default: the latest recommended size")


class SchemeResult(BaseModel):
    scheme_id: str
    name: str
    jurisdiction: str
    kind: str
    eligible: Eligible
    reasons: list[str]
    conditions: list[str]
    amount_inr: float | None  # capital subsidy for this size, when it counts
    inr_per_kwh: float | None  # generation incentive rate, when it counts
    incentive_years: int | None
    counts_in_estimate: bool
    status: str
    source_url: str
    verified_on: date
    review_by: date | None


class EligibilityResponse(BaseModel):
    user_id: str
    capacity_kwp: float | None
    schemes: list[SchemeResult]
    total_subsidy_inr: float
    notes: list[str]
    disclaimer: str
