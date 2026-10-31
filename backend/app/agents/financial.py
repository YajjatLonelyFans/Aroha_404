"""Financial agent: explains the latest solar estimate (cost, savings, payback)."""

from app.agents.contracts import AgentContext, AgentOutput, MemoryCandidate, inr, num

BINDING = {
    "roof": "limited by what fits on the roof",
    "consumption": "sized to the household's electricity use",
    "limit": "capped by a scheme or DISCOM limit",
}


def _range(r: dict, money: bool) -> str:
    fmt = inr if money else (lambda v: num(v, 1))
    return f"{fmt(r['likely'])} (range {fmt(r['low'])}–{fmt(r['high'])})"


async def run(ctx: AgentContext) -> AgentOutput:
    e = ctx.estimate
    if e is None:
        return AgentOutput(agent="financial", status="partial",
                           facts=["No cost and savings estimate yet; the results step gives this after the roof check."])

    facts = [f"Recommended size {e['recommended_kwp']} kW, {BINDING.get(e['binding_constraint'], '')}; "
             f"the roof fits up to {e['roof_kwp']} kW and the household's use needs about {e['consumption_kwp']} kW."]
    rec = None
    for o in e["options"]:
        line = (f"{o['capacity_kwp']} kW: about {num(o['annual_kwh']['median'])} kWh a year, "
                f"cost {inr(o['gross_cost_inr'])}, saves about {inr(o['annual_savings_inr']['likely'])} a year, "
                f"payback about {num(o['payback_years']['likely'], 1)} years")
        facts.append(line + (" (recommended)." if o["recommended"] else "."))
        if o["recommended"]:
            rec = o
    if rec is not None:
        facts.append(f"For {rec['capacity_kwp']} kW, yearly savings are {_range(rec['annual_savings_inr'], True)} "
                     f"and payback is {_range(rec['payback_years'], False)} years.")
        facts += rec.get("missing", [])
    facts += e.get("notes", [])
    if ctx.assessment is not None and e["assessment_id"] != ctx.assessment["id"]:
        # Consistency check: money must describe the same roof the roof agent is talking about.
        facts.append("This estimate was made for an earlier roof drawing; run the estimate again for the latest roof.")
    facts.append(e["disclaimer"])

    memory = []
    if rec is not None:
        memory.append(MemoryCandidate(
            agent="financial",
            record_id=e["id"],
            text=(f"Estimate: recommended {rec['capacity_kwp']} kW ({e['binding_constraint']}); about "
                  f"{num(rec['annual_kwh']['median'])} kWh a year; saves about "
                  f"{inr(rec['annual_savings_inr']['likely'])} a year; payback about "
                  f"{num(rec['payback_years']['likely'], 1)} years before subsidy."),
        ))
    return AgentOutput(
        agent="financial",
        status="ok",
        result={"estimate_id": e["id"], "recommended_kwp": e["recommended_kwp"],
                "binding_constraint": e["binding_constraint"],
                "options": [{k: o[k] for k in ("capacity_kwp", "gross_cost_inr", "annual_savings_inr", "payback_years")}
                            for o in e["options"]]},
        facts=facts,
        assumptions=e.get("assumptions", []),
        memory_writes=memory,
        is_mock=bool(e.get("is_mock")),
    )
