"""Synthetic Open-Meteo-shaped data shared by weather tests."""

import json
from datetime import date, datetime, timedelta, timezone

from app.core.assumptions import ASSUMPTIONS_PATH, Assumptions
from app.integrations.weather.base import CurrentConditions, HourlySeries, SourceInfo


def hourly_times(start: date, end: date) -> list[str]:
    out, day = [], start
    while day <= end:
        out += [f"{day.isoformat()}T{h:02d}:00" for h in range(24)]
        day += timedelta(days=1)
    return out


def hourly_body(start: date, end: date, gti_day: float = 500.0) -> dict:
    """Archive/forecast response: GTI `gti_day` W/m² from 06:00 to 17:59, else 0."""
    times = hourly_times(start, end)
    hours = [int(t[11:13]) for t in times]
    return {
        "hourly_units": {"global_tilted_irradiance": "W/m²", "temperature_2m": "°C"},
        "hourly": {
            "time": times,
            "global_tilted_irradiance": [gti_day if 6 <= h < 18 else 0.0 for h in hours],
            "temperature_2m": [25.0] * len(times),
            "cloud_cover": [30.0] * len(times),
            "precipitation": [0.1] * len(times),
            "sunshine_duration": [1800.0] * len(times),
        },
    }


def series(start: date, end: date, *, is_mock: bool = False, gti_day: float = 500.0) -> HourlySeries:
    h = hourly_body(start, end, gti_day)["hourly"]
    return HourlySeries(
        times=h["time"],
        values={k: v for k, v in h.items() if k != "time"},
        units={},
        source=SourceInfo("Test weather", "test://", datetime(2026, 11, 1, tzinfo=timezone.utc), is_mock),
    )


def assumptions(**sections) -> Assumptions:
    """Shipped assumptions with selected sections overridden, e.g. module={"gamma_per_c": -0.004}."""
    data = json.loads(ASSUMPTIONS_PATH.read_text(encoding="utf-8"))
    for name, values in sections.items():
        data[name].update(values)
    return Assumptions.model_validate(data)


# Tests start from these so they do not depend on how much of the shipped file is filled in.
UNSET = {
    "module": {"gamma_per_c": None, "noct_c": None},
    "losses": {"l_other_fraction": None},
    "forecast": {"sunny_min_ratio": None, "cloudy_max_ratio": None, "rain_min_mm": None},
}
YIELD_READY = {
    "module": {"gamma_per_c": -0.004, "noct_c": 45},
    "losses": {"l_other_fraction": 0.14},
}
# Every value Stage 4 needs. Illustrative numbers for tests only, not real Delhi figures.
JOURNEY_READY = {
    "module": {"length_m": 2.0, "width_m": 1.0, "wp": 500, "gamma_per_c": -0.004, "noct_c": 45},
    "layout": {"edge_setback_m": 0.5, "no_go_clearance_m": 0.0, "row_gap_m": 0.5, "flush_gap_m": 0.05,
               "default_flat_tilt_deg": 20, "default_azimuth_deg": 0},
    "capacity": {"shading_haircut_fraction": 0.25, "small_area_m2": 10, "many_obstructions_fraction": 0.3,
                 "large_outline_m2": 420, "min_recommended_kwp": 1.0},
    "losses": {"l_other_fraction": 0.14, "shading_by_level": {"none": 0.0, "partial": 0.05, "heavy": 0.15},
               "shading_cap_fraction": 0.25},
    "costs": {"cost_per_kwp_inr": 60000},
    "tariff": {"discoms": ["BRPL", "BYPL", "TPDDL", "NDMC"], "export_rate_inr": 3.0,
               "slabs": [{"up_to_kwh": 200, "rate_inr_per_kwh": 3.0}, {"up_to_kwh": 400, "rate_inr_per_kwh": 4.5},
                         {"up_to_kwh": None, "rate_inr_per_kwh": 6.5}]},
    "validation": {"min_outline_m2": 10, "max_outline_m2": 2000},
}
OUTLOOK_READY = {"forecast": {"sunny_min_ratio": 0.9, "cloudy_max_ratio": 0.5, "rain_min_mm": 5}}


def current_conditions(is_mock: bool = False) -> CurrentConditions:
    return CurrentConditions(
        time="2026-11-01T12:00",
        values={"temperature_2m": 24.5, "relative_humidity_2m": 40, "precipitation": 0.0,
                "cloud_cover": 10, "wind_speed_10m": 6.1, "is_day": 1},
        units={},
        source=SourceInfo("Test weather", "test://", datetime(2026, 11, 1, tzinfo=timezone.utc), is_mock),
    )
