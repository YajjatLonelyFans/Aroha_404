"""Recommended size, cost, subsidy, savings and payback.

Missing inputs give `None` plus a reason; nothing is guessed.
"""

import math
from dataclasses import dataclass, field
from typing import Literal

from app.domain.errors import DomainError
from app.domain.generation import Percentiles

BindingConstraint = Literal["roof", "consumption", "limit"]


@dataclass(frozen=True)
class Slab:
    up_to_kwh: float | None  # None = no upper limit (last slab)
    rate_inr_per_kwh: float


@dataclass(frozen=True)
class SizeRecommendation:
    roof_kwp: float
    consumption_kwp: float
    recommended_kwp: float
    panel_count: int
    binding_constraint: BindingConstraint


@dataclass(frozen=True)
class Range:
    low: float | None
    likely: float | None
    high: float | None


@dataclass(frozen=True)
class FinanceResult:
    capacity_kwp: float
    gross_cost_inr: float | None
    subsidy_inr: float
    net_cost_inr: float | None
    annual_savings_inr: Range
    payback_years: Range
    missing: list[str] = field(default_factory=list)  # reasons a figure is None


# --- Sizing ------------------------------------------------------------------------------


def recommend_size(
    *,
    roof_panel_count: int,
    module_wp: float,
    annual_consumption_kwh: float,
    annual_yield_kwh_per_kwp: float,
    limit_kwp: float | None = None,
) -> SizeRecommendation:
    """Smaller of what fits on the roof and what the household uses, in whole modules."""
    if module_wp <= 0:
        raise DomainError("invalid_module", "Module wattage must be positive.")
    if annual_yield_kwh_per_kwp <= 0:
        raise DomainError("invalid_yield", "Specific yield must be positive to size the system.")
    if annual_consumption_kwh < 0:
        raise DomainError("invalid_consumption", "Consumption cannot be negative.")

    kw_per_module = module_wp / 1000
    consumption_kwp = annual_consumption_kwh / annual_yield_kwh_per_kwp
    candidates: list[tuple[int, BindingConstraint]] = [
        (roof_panel_count, "roof"),
        (round(consumption_kwp / kw_per_module), "consumption"),
    ]
    if limit_kwp is not None:
        candidates.append((math.floor(limit_kwp / kw_per_module + 1e-9), "limit"))
    count, binding = min(candidates, key=lambda c: c[0])  # first listed wins a tie

    return SizeRecommendation(
        roof_kwp=round(roof_panel_count * kw_per_module, 3),
        consumption_kwp=consumption_kwp,
        recommended_kwp=round(count * kw_per_module, 3),
        panel_count=count,
        binding_constraint=binding,
    )


def payback_with_incentive(
    net_cost_inr: float, annual_savings_inr: float, annual_incentive_inr: float, incentive_years: int
) -> float | None:
    """Simple payback when a yearly incentive is paid on top of savings for a limited number of years."""
    if net_cost_inr <= 0:
        return 0.0
    early = annual_savings_inr + annual_incentive_inr
    if early > 0 and net_cost_inr <= early * incentive_years:
        return net_cost_inr / early
    if annual_savings_inr <= 0:
        return None
    remaining = net_cost_inr - max(early, 0) * incentive_years
    return incentive_years + remaining / annual_savings_inr


# --- Tariff and savings ------------------------------------------------------------------


def energy_charge_inr(units_kwh: float, slabs: list[Slab]) -> float:
    """Monthly energy charge with telescopic slabs (each rate applies to units inside its slab)."""
    if not slabs:
        raise DomainError("missing_tariff", "No tariff slabs.")
    charge, lower = 0.0, 0.0
    for slab in slabs:
        upper = math.inf if slab.up_to_kwh is None else slab.up_to_kwh
        if units_kwh > lower:
            charge += (min(units_kwh, upper) - lower) * slab.rate_inr_per_kwh
        lower = upper
        if units_kwh <= lower:
            break
    if units_kwh > lower:
        raise DomainError("invalid_tariff", "The last tariff slab must have no upper limit.")
    return charge


def monthly_saving_inr(
    generation_kwh: float, consumption_kwh: float, slabs: list[Slab], export_rate_inr: float
) -> float:
    """Avoided energy charge on self-used units (taken off the top slabs) plus export credit."""
    self_used = min(generation_kwh, consumption_kwh)
    exported = max(generation_kwh - consumption_kwh, 0.0)
    avoided = energy_charge_inr(consumption_kwh, slabs) - energy_charge_inr(
        consumption_kwh - self_used, slabs
    )
    return avoided + exported * export_rate_inr


def estimate_finance(
    *,
    capacity_kwp: float,
    monthly_kwh: tuple[Percentiles, ...],
    monthly_consumption_kwh: float,
    cost_per_kwp_inr: float | None,
    subsidy_inr: float,
    slabs: list[Slab],
    export_rate_inr: float | None,
) -> FinanceResult:
    if len(monthly_kwh) != 12:
        raise DomainError("invalid_series", "Need 12 months of generation.")
    if subsidy_inr < 0:
        raise DomainError("invalid_subsidy", "Subsidy cannot be negative.")
    missing: list[str] = []

    gross = net = None
    if cost_per_kwp_inr is None:
        missing.append("Installed cost per kWp is not set.")
    else:
        gross = capacity_kwp * cost_per_kwp_inr
        net = max(gross - subsidy_inr, 0.0)

    savings: dict[str, float | None] = {"low": None, "likely": None, "high": None}
    if not slabs or export_rate_inr is None:
        missing.append("Tariff slabs or export rate are not set.")
    elif any(p.median is None for p in monthly_kwh):
        missing.append("Generation is missing for at least one month.")
    else:
        for key, attr in (("low", "p10"), ("likely", "median"), ("high", "p90")):
            savings[key] = sum(
                monthly_saving_inr(getattr(p, attr), monthly_consumption_kwh, slabs, export_rate_inr)
                for p in monthly_kwh
            )

    def payback(saving: float | None) -> float | None:
        if net is None or saving is None:
            return None
        if net == 0:
            return 0.0
        return net / saving if saving > 0 else None

    if net is not None and net > 0 and savings["likely"] is not None and savings["likely"] <= 0:
        missing.append("No savings expected, so there is no payback.")

    return FinanceResult(
        capacity_kwp=capacity_kwp,
        gross_cost_inr=gross,
        subsidy_inr=subsidy_inr,
        net_cost_inr=net,
        annual_savings_inr=Range(savings["low"], savings["likely"], savings["high"]),
        # Higher savings → shorter payback, so the range flips.
        payback_years=Range(payback(savings["high"]), payback(savings["likely"]), payback(savings["low"])),
        missing=missing,
    )
