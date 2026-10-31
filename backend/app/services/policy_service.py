"""Scheme eligibility and the subsidy figures that feed the estimate."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.errors import NotFoundError
from app.db import collections as c
from app.db.store import DocumentStore
from app.domain.policy import Profile, capital_amount_inr, check, incentive_rate
from app.domain.units import round_inr
from app.schemas.policy import EligibilityRequest, EligibilityResponse, PolicyRecord, SchemeResult
from app.services.weather_service import utc_now

DISCLAIMER = (
    "Eligibility here is a guide from dated official records. The subsidy and the DISCOM connection are "
    "decided by the authorities; Aroha does not apply on your behalf or promise approval."
)


@dataclass
class PolicyMoney:
    """What the verified, eligible schemes add for one system size."""

    subsidy_inr: float = 0.0
    breakdown: list[dict[str, Any]] = field(default_factory=list)
    inr_per_kwh: float | None = None
    incentive_years: int | None = None
    record_ids: list[str] = field(default_factory=list)


def profile_of(user: dict[str, Any], capacity_kwp: float | None) -> Profile:
    return Profile(
        property_type=user["property_type"],
        has_roof_rights=user["has_roof_rights"],
        discom=user["discom"],
        monthly_units_kwh=user["monthly_units_kwh"],
        capacity_kwp=capacity_kwp,
    )


class PolicyService:
    def __init__(self, store: DocumentStore, clock: Callable[[], datetime] = utc_now) -> None:
        self._store = store
        self._clock = clock

    async def records(self) -> list[tuple[str, PolicyRecord]]:
        docs = await self._store.find(c.POLICY_RECORDS, {})
        out = []
        for d in docs:
            doc_id = d.pop("id")
            out.append((doc_id, PolicyRecord.model_validate(d)))
        return sorted(out, key=lambda r: (r[1].jurisdiction, r[1].scheme_id))

    async def evaluate(self, user: dict[str, Any], capacity_kwp: float | None) -> list[SchemeResult]:
        today = self._clock().date()
        profile = profile_of(user, capacity_kwp)
        results = []
        for _, rec in await self.records():
            e = check(rec, profile, today)
            amount = rate = None
            if e.counts_in_estimate and capacity_kwp is not None:
                if rec.kind == "capital_subsidy":
                    amount = round_inr(capital_amount_inr(rec.amount_rule, capacity_kwp))
                elif rec.kind == "generation_incentive":
                    rate = incentive_rate(rec.amount_rule, capacity_kwp)
            results.append(SchemeResult(
                scheme_id=rec.scheme_id, name=rec.name, jurisdiction=rec.jurisdiction, kind=rec.kind,
                eligible=e.eligible, reasons=e.reasons, conditions=rec.rules.conditions,
                amount_inr=amount, inr_per_kwh=rate,
                incentive_years=rec.amount_rule.years if rate is not None else None,
                counts_in_estimate=e.counts_in_estimate and (amount is not None or rate is not None),
                status=rec.status, source_url=rec.source_url, verified_on=rec.verified_on, review_by=rec.review_by,
            ))
        return results

    async def money_for(self, user: dict[str, Any], capacity_kwp: float) -> PolicyMoney:
        ids = {rec.scheme_id: doc_id for doc_id, rec in await self.records()}
        money = PolicyMoney()
        for s in await self.evaluate(user, capacity_kwp):
            if not s.counts_in_estimate:
                continue
            money.record_ids.append(ids[s.scheme_id])
            if s.amount_inr is not None:
                money.subsidy_inr += s.amount_inr
                money.breakdown.append({"scheme_id": s.scheme_id, "name": s.name, "amount_inr": s.amount_inr})
            if s.inr_per_kwh is not None:
                money.inr_per_kwh, money.incentive_years = s.inr_per_kwh, s.incentive_years
        return money

    async def eligibility(self, req: EligibilityRequest) -> EligibilityResponse:
        user = await self._store.get(c.USERS, req.user_id)
        if user is None:
            raise NotFoundError("User")
        capacity = req.capacity_kwp
        notes = []
        if capacity is None:
            estimate = await self._store.latest(c.SOLAR_ESTIMATES, {"user_id": req.user_id})
            if estimate is not None:
                capacity = estimate["recommended_kwp"]
                notes.append(f"Amounts are for the recommended {capacity} kW system.")
            else:
                notes.append("No system size yet, so amounts are not shown; get an estimate first.")
        schemes = await self.evaluate(user, capacity)
        if any(s.status != "verified" for s in schemes):
            notes.append("Schemes marked 'needs verification' are shown for information and never counted.")
        return EligibilityResponse(
            user_id=req.user_id,
            capacity_kwp=capacity,
            schemes=schemes,
            total_subsidy_inr=sum(s.amount_inr or 0 for s in schemes if s.counts_in_estimate),
            notes=notes,
            disclaimer=DISCLAIMER,
        )
