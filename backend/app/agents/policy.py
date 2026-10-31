"""Policy and eligibility agent: explains which schemes apply, with sources and verified-on dates."""

from app.agents.contracts import AgentContext, AgentOutput, MemoryCandidate, inr
from app.core.errors import AppError
from app.services.policy_service import DISCLAIMER, PolicyService

LABEL = {"yes": "you appear eligible", "no": "not eligible", "unknown": "needs verification"}


async def run(ctx: AgentContext, policy: PolicyService) -> AgentOutput:
    if not ctx.resumed:
        return AgentOutput(agent="policy", status="partial",
                           facts=["Subsidy eligibility needs your home's details first."])
    capacity = ctx.estimate["recommended_kwp"] if ctx.estimate else None
    try:
        schemes = await policy.evaluate(ctx.user, capacity)
    except AppError as exc:
        return AgentOutput(agent="policy", status="error", error=exc.message,
                           facts=["Scheme records could not be loaded just now."])

    facts = []
    for s in schemes:
        line = f"{s.name}: {LABEL[s.eligible]}"
        if s.amount_inr is not None:
            line += f", about {inr(s.amount_inr)} for {capacity} kW"
        if s.inr_per_kwh is not None:
            line += f", {inr(s.inr_per_kwh)} per unit generated for {s.incentive_years} years"
        if s.eligible != "yes":
            line += f" ({' '.join(s.reasons)})"
        facts.append(f"{line}. Source checked on {s.verified_on:%d %b %Y}: {s.source_url}")
    total = sum(s.amount_inr or 0 for s in schemes if s.counts_in_estimate)
    if capacity is not None:
        facts.append(f"Verified subsidies for {capacity} kW total {inr(total)}.")
    else:
        facts.append("Amounts appear once a system size is estimated.")
    facts.append(DISCLAIMER)

    summary = "; ".join(
        f"{s.scheme_id} {s.eligible}" + (f" {inr(s.amount_inr)}" if s.amount_inr is not None else "")
        for s in schemes
    )
    return AgentOutput(
        agent="policy",
        status="ok",
        result={"capacity_kwp": capacity, "total_subsidy_inr": total,
                "schemes": [s.model_dump(mode="json") for s in schemes]},
        facts=facts,
        memory_writes=[MemoryCandidate(agent="policy", record_id=f"policy|{capacity}|{summary}",
                                       text=f"Schemes checked for {capacity} kW: {summary}.")],
    )
