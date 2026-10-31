"""Scheme eligibility and amounts from policy records (pure; today's date is passed in).

A record counts towards money only when it is verified, its review date has not
passed, and every checkable rule is met. Anything else is shown, never counted.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.schemas.policy import AmountRule, PolicyRecord

Eligible = Literal["yes", "no", "unknown"]

PROPERTY_LABELS = {"independent_house": "independent house", "builder_floor": "builder floor", "other": "other property"}


@dataclass(frozen=True)
class Profile:
    property_type: str
    has_roof_rights: bool
    discom: str
    monthly_units_kwh: float
    capacity_kwp: float | None  # None until a size has been chosen


@dataclass(frozen=True)
class Eligibility:
    eligible: Eligible
    reasons: list[str] = field(default_factory=list)
    counts_in_estimate: bool = False


def capital_amount_inr(rule: AmountRule, capacity_kwp: float) -> float:
    """Capital subsidy for a system size: tiered or flat per kW, then capped."""
    if rule.type == "tiered_per_kwp":
        total, lower = 0.0, 0.0
        for tier in rule.tiers:
            if capacity_kwp > lower:
                total += (min(capacity_kwp, tier.up_to_kwp) - lower) * (tier.inr_per_kwp or 0.0)
            lower = tier.up_to_kwp
    elif rule.type == "per_kwp":
        total = capacity_kwp * (rule.inr_per_kwp or 0.0)
    else:
        return 0.0
    return min(total, rule.cap_inr) if rule.cap_inr is not None else total


def incentive_rate(rule: AmountRule, capacity_kwp: float) -> float | None:
    """Generation incentive per kWh for a system size, or None if the size is outside every tier."""
    if rule.type != "gbi":
        return None
    for tier in rule.tiers:
        if capacity_kwp <= tier.up_to_kwp:
            return tier.inr_per_kwh
    return None


def check(record: PolicyRecord, profile: Profile, today: date) -> Eligibility:
    if record.status == "expired":
        return Eligibility("no", ["This scheme has ended."])
    if record.status != "verified":
        return Eligibility("unknown", ["Needs verification: not yet confirmed on an official page, so it is not counted."])
    if record.review_by is not None and record.review_by < today:
        return Eligibility("unknown", [f"Needs re-verification: the record was due for review on {record.review_by}."])

    r = record.rules
    failed: list[str] = []
    if r.requires_roof_rights and not profile.has_roof_rights:
        failed.append("You need the right to use the roof.")
    if profile.property_type not in r.eligible_property_types:
        failed.append(f"It covers {', '.join(PROPERTY_LABELS.get(p, p) for p in r.eligible_property_types)} only.")
    if r.discoms is not None and profile.discom not in r.discoms:
        failed.append(f"It applies to {', '.join(r.discoms)} consumers.")
    if r.max_monthly_units_kwh is not None and profile.monthly_units_kwh > r.max_monthly_units_kwh:
        failed.append(f"It is for homes using up to {r.max_monthly_units_kwh:g} units a month.")
    if failed:
        return Eligibility("no", failed)

    if r.capacity_kwp_max is not None:
        if profile.capacity_kwp is None:
            return Eligibility("unknown", ["Depends on the system size; get an estimate first."])
        if profile.capacity_kwp > r.capacity_kwp_max:
            return Eligibility("no", [f"It covers systems up to {r.capacity_kwp_max:g} kW."])

    return Eligibility("yes", ["Meets the scheme's rules for property type, roof rights and DISCOM."], True)
