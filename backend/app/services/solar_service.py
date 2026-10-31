"""Solar estimate: generation range and money for 1-3 capacities, from one roof assessment.

Generation and money are computed together so they never drift apart.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.core.assumptions import Assumptions
from app.core.errors import AppError, NotFoundError
from app.db import collections as c
from app.db.store import DocumentStore
from app.domain.errors import DomainError
from app.domain.finance import Slab, estimate_finance, recommend_size
from app.domain.generation import SpecificYield, median_annual_yield, monthly_generation
from app.domain.units import round_inr, round_kwh, round_kwp, round_pct, round_years
from app.schemas.common import Source
from app.schemas.solar import (
    Band,
    EstimateOption,
    MonthKwh,
    Range,
    SolarEstimateRequest,
    SolarEstimateResponse,
)
from app.services.weather_service import (
    ATTRIBUTION,
    WeatherService,
    specific_yield_from_doc,
    utc_now,
)

MODEL_VERSION = "gen-1.0.0"
NEIGHBOUR_STEP_KWP = 1.0  # default options: recommended size and about 1 kW either side
DISCLAIMER = (
    "These are estimates, not guarantees. Generation is a range based on past weather; "
    "savings depend on your actual use and tariff. Subsidy and DISCOM approval are decided by the authorities."
)


def _r(value: float | None, fn: Callable[[float], float]) -> float | None:
    return None if value is None else fn(value)


def option_counts(
    recommended: int, roof_max: int, module_wp: float, requested_kwp: list[float] | None
) -> list[int]:
    """Panel counts to compare: the user's sizes, or the recommended size and its neighbours."""
    if requested_kwp:
        counts = []
        for kwp in requested_kwp:
            n = round(kwp * 1000 / module_wp)
            if n < 1:
                raise DomainError("capacity_too_small", f"{kwp:g} kWp is less than one panel.")
            if n > roof_max:
                raise DomainError(
                    "capacity_exceeds_roof",
                    f"{kwp:g} kWp does not fit; the roof holds up to {round_kwp(roof_max * module_wp / 1000):g} kWp.",
                )
            counts.append(n)
        return sorted(set(counts))
    step = max(1, round(NEIGHBOUR_STEP_KWP * 1000 / module_wp))
    return sorted({n for n in (recommended - step, recommended, recommended + step) if 1 <= n <= roof_max})


class SolarService:
    def __init__(
        self,
        store: DocumentStore,
        weather: WeatherService,
        assumptions: Assumptions,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._store = store
        self._weather = weather
        self._a = assumptions
        self._clock = clock

    async def estimate(self, req: SolarEstimateRequest) -> SolarEstimateResponse:
        a = self._a
        user = await self._store.get(c.USERS, req.user_id)
        if user is None:
            raise NotFoundError("User")
        assessment = await self._store.get(c.ROOF_ASSESSMENTS, req.assessment_id)
        if assessment is None or assessment["user_id"] != req.user_id:
            raise NotFoundError("Roof assessment")
        prop = await self._store.get(c.PROPERTIES, assessment["property_id"])
        if prop is None:
            raise NotFoundError("Property")

        roof_max = assessment["panel_count"]
        if roof_max < 1:
            raise DomainError("no_panels_fit", "No full panel fits on this roof, so there is nothing to estimate.")
        module_wp = assessment["module_wp"]
        shade = assessment["shading_loss_fraction"]
        monthly_units = req.monthly_units_kwh or user["monthly_units_kwh"]

        lon, lat = prop["pin"]["coordinates"]
        clim, _, notes = await self._weather.climatology_doc(
            lat, lon, assessment["array_tilt_deg"], assessment["array_azimuth_deg"]
        )
        base = specific_yield_from_doc(clim)
        if base is None:
            raise AppError(
                "yield_unavailable",
                "Energy per kWp is not available: set module.gamma_per_c, module.noct_c and "
                "losses.l_other_fraction in the assumptions file.",
                status_code=503,
            )
        # Output is linear in (1 - shade), so the shade loss scales the stored yield once.
        sy = SpecificYield(base.years, base.kwh_per_kwp * (1 - shade), base.missing_hours, base.excluded)
        annual_yield = median_annual_yield(sy)
        if annual_yield is None:
            raise AppError("yield_unavailable", "Not enough complete years of weather data.", status_code=503)

        size = recommend_size(
            roof_panel_count=roof_max,
            module_wp=module_wp,
            annual_consumption_kwh=monthly_units * 12,
            annual_yield_kwh_per_kwp=annual_yield,
        )
        recommended = max(size.panel_count, 1)
        counts = option_counts(recommended, roof_max, module_wp, req.capacities_kwp)

        slabs: list[Slab] = []
        if a.tariff.discom == user["discom"]:
            slabs = [Slab(s.up_to_kwh, s.rate_inr_per_kwh) for s in a.tariff.slabs]
        else:
            notes.append(
                f"Savings need the {user['discom']} tariff, but the assumptions file has {a.tariff.discom} only."
            )
        notes.append("Subsidies are not applied yet; verified scheme records come in a later step.")

        options: list[EstimateOption] = []
        for n in counts:
            kwp = n * module_wp / 1000
            gen = monthly_generation(kwp, sy)
            fin = estimate_finance(
                capacity_kwp=kwp,
                monthly_kwh=gen.monthly_kwh,
                monthly_consumption_kwh=monthly_units,
                cost_per_kwp_inr=a.costs.cost_per_kwp_inr,
                subsidy_inr=0.0,
                slabs=slabs,
                export_rate_inr=a.tariff.export_rate_inr,
            )
            options.append(EstimateOption(
                capacity_kwp=round_kwp(kwp),
                panel_count=n,
                recommended=n == recommended,
                monthly_kwh=[
                    MonthKwh(month=m + 1, p10=_r(p.p10, round_kwh), median=_r(p.median, round_kwh),
                             p90=_r(p.p90, round_kwh))
                    for m, p in enumerate(gen.monthly_kwh)
                ],
                annual_kwh=Band(p10=_r(gen.annual_kwh.p10, round_kwh), median=_r(gen.annual_kwh.median, round_kwh),
                                p90=_r(gen.annual_kwh.p90, round_kwh)),
                gross_cost_inr=_r(fin.gross_cost_inr, round_inr),
                subsidy_inr=round_inr(fin.subsidy_inr),
                net_cost_inr=_r(fin.net_cost_inr, round_inr),
                annual_savings_inr=Range(**{k: _r(getattr(fin.annual_savings_inr, k), round_inr)
                                            for k in ("low", "likely", "high")}),
                payback_years=Range(**{k: _r(getattr(fin.payback_years, k), round_years)
                                       for k in ("low", "likely", "high")}),
                missing=fin.missing,
            ))

        assumptions = [
            f"Energy per kWp from {clim['period']} hourly weather history for this spot; "
            f"shade lowers it by {round_pct(100 * shade):g}%.",
            f"Losses other than heat and shade: {round_pct(100 * a.losses.l_other_fraction):g}%.",
            f"Same use every month: {monthly_units:g} units.",
            "Simple payback: no panel ageing, tariff rises or loan cost.",
        ]
        if a.costs.cost_per_kwp_inr is not None:
            assumptions.append(f"Installed cost {a.costs.cost_per_kwp_inr:,.0f} INR per kWp (as of {a.costs.as_of}).")
        if slabs and a.tariff.export_rate_inr is not None:
            assumptions.append(
                f"{a.tariff.discom} slab tariff as of {a.tariff.as_of}; "
                f"units sent to the grid credited at {a.tariff.export_rate_inr:g} INR each."
            )

        snapshot = {
            "module_wp": module_wp,
            "l_other_fraction": a.losses.l_other_fraction,
            "shading_loss_fraction": shade,
            "cost_per_kwp_inr": a.costs.cost_per_kwp_inr,
            "tariff": a.tariff.model_dump(mode="json") if slabs else None,
            "annual_yield_kwh_per_kwp": annual_yield,
        }
        response_fields: dict[str, Any] = {
            "assessment_id": req.assessment_id,
            "climatology_id": str(clim.get("_id") or ""),
            "monthly_units_kwh": monthly_units,
            "options": [o.model_dump() for o in options],
            "recommended_kwp": round_kwp(recommended * module_wp / 1000),
            "binding_constraint": size.binding_constraint,
            "roof_kwp": round_kwp(size.roof_kwp),
            "consumption_kwp": round_kwp(size.consumption_kwp),
            "shading_loss_fraction": shade,
            "assumptions": assumptions,
            "notes": notes,
            "disclaimer": DISCLAIMER,
            "assumptions_version": a.version,
            "model_version": MODEL_VERSION,
            "is_mock": bool(clim.get("is_mock")),
        }
        estimate_id = await self._store.insert(c.SOLAR_ESTIMATES, {
            **response_fields,
            "user_id": req.user_id,
            "property_id": assessment["property_id"],
            "policy_record_ids": [],
            "assumptions_snapshot": snapshot,
            "created_at": self._clock(),
        })

        src = clim["source"]
        return SolarEstimateResponse(
            estimate_id=estimate_id,
            sources=[Source(name=src["name"], url=src.get("url"), retrieved_at=src["retrieved_at"], note=ATTRIBUTION)],
            **response_fields,
        )
