"""Roof agent: explains the latest roof assessment."""

from app.agents.contracts import AgentContext, AgentOutput, MemoryCandidate, num
from app.domain.units import round_pct


async def run(ctx: AgentContext) -> AgentOutput:
    a = ctx.assessment
    if a is None:
        return AgentOutput(agent="roof", status="partial",
                           facts=["No roof has been traced yet; the roof step on the map gives this."])

    kwp = a["capacity_kwp"]
    shade_pct = round_pct(100 * a["shading_loss_fraction"])
    spread = f" (range {kwp['min']}–{kwp['max']} kW)" if kwp["min"] != kwp["max"] else ""
    facts = [
        f"Roof outline {num(a['outline_area_m2'], 1)} m²; after {num(a['setback_area_m2'], 1)} m² of edge walkway "
        f"and {num(a['no_go_area_m2'], 1)} m² of tanks and stair rooms, {num(a['usable_area_m2'], 1)} m² is usable.",
        f"{a['panel_count']} panels of {num(a['module_wp'])} W fit, about {kwp['likely']} kW{spread}.",
        f"Shade lowers output by {shade_pct:g}%; confidence in the roof estimate is {a['confidence']}.",
    ]
    facts += [c["message"] for c in a.get("constraints", [])]
    return AgentOutput(
        agent="roof",
        status="ok",
        result={k: a[k] for k in ("usable_area_m2", "panel_count", "capacity_kwp", "shading_loss_fraction")},
        facts=facts,
        assumptions=a.get("assumptions", []),
        confidence=a["confidence"],
        memory_writes=[MemoryCandidate(
            agent="roof",
            record_id=a["id"],
            text=(f"Roof assessed: {num(a['usable_area_m2'], 1)} m² usable, fits {a['panel_count']} panels "
                  f"({kwp['likely']} kW); shade loss {shade_pct:g}%; confidence {a['confidence']}."),
        )],
    )
