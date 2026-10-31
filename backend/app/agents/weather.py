"""Weather and solar-conditions agent: explains the climatology and, when asked, the short-term outlook."""

from app.agents.contracts import AgentContext, AgentOutput, MemoryCandidate, num
from app.core.errors import AppError
from app.domain.units import month_name
from app.services.weather_service import WeatherService


async def run(ctx: AgentContext, weather: WeatherService) -> AgentOutput:
    if ctx.property is None or ctx.assessment is None:
        return AgentOutput(agent="weather", status="partial",
                           facts=["The home's location and roof are needed before weather can be checked."])
    lon, lat = ctx.property["pin"]["coordinates"]
    tilt, azimuth = ctx.assessment["array_tilt_deg"], ctx.assessment["array_azimuth_deg"]
    try:
        clim = await weather.climatology(lat, lon, tilt, azimuth)
    except AppError as exc:
        return AgentOutput(agent="weather", status="error", error=exc.message,
                           facts=["Weather history could not be loaded just now."])

    facts = [f"Based on hourly weather history for {clim.period} at this spot."]
    if clim.specific_yield is not None:
        y = clim.specific_yield.annual_kwh_per_kwp
        facts.append(f"Each kW of panels makes about {num(y.median)} kWh a year here "
                     f"(range {num(y.p10)}–{num(y.p90)} kWh across years).")
    facts += [n.statement for n in clim.season_notes]

    if ctx.wants_forecast:
        try:
            fc = await weather.forecast(lat, lon, tilt, azimuth)
            days = ", ".join(f"{d.date[5:]} {d.outlook or 'unlabelled'}" for d in fc.daily)
            facts.append(f"Short-term outlook (not used in any estimate): {days}.")
        except AppError:
            facts.append("The short-term outlook is unavailable right now.")

    sunniest = max((m for m in clim.monthly if m.gti_kwh_m2.median is not None),
                   key=lambda m: m.gti_kwh_m2.median, default=None)
    memory = []
    if clim.specific_yield is not None and sunniest is not None:
        memory.append(MemoryCandidate(
            agent="weather",
            record_id=clim.climatology_id or None,
            text=(f"Weather for this home ({clim.period}): about "
                  f"{num(clim.specific_yield.annual_kwh_per_kwp.median)} kWh per kW a year; "
                  f"sunniest month {month_name(sunniest.month)}."),
        ))
    return AgentOutput(
        agent="weather",
        status="ok",
        result={"climatology_id": clim.climatology_id, "period": clim.period,
                "annual_kwh_per_kwp": clim.specific_yield.annual_kwh_per_kwp.model_dump()
                if clim.specific_yield else None},
        facts=facts,
        assumptions=clim.assumptions,
        sources=clim.sources,
        memory_writes=memory,
        is_mock=clim.is_mock,
    )
