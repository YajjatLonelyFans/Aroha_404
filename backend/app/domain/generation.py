"""PV generation from hourly plane-of-array irradiance and air temperature.

Per hour h:
    T_cell = T_air + (NOCT − 20) / 800 × G
    P_dc   = kWp × (G / 1000) × (1 + γ × (T_cell − 25))
    P_ac   = max(P_dc, 0) × (1 − L_other) × (1 − L_shade)

Temperature loss enters only through γ; L_other must exclude it. ERA5 GTI
carries no PV losses, so nothing is counted twice. Output is linear in kWp,
so the work is done once per kWp ("specific yield") and scaled.
"""

import calendar
from dataclasses import dataclass

import numpy as np

from app.domain.errors import DomainError


@dataclass(frozen=True)
class GenerationParams:
    gamma_per_c: float  # temperature coefficient of Pmax, per °C (negative)
    noct_c: float
    l_other_fraction: float  # soiling, wiring, mismatch, inverter, availability; not temperature
    l_shade_fraction: float  # from the roof assessment


@dataclass(frozen=True)
class SpecificYield:
    """kWh per kWp for each (year, month). Months with too much missing data are NaN."""

    years: tuple[int, ...]
    kwh_per_kwp: np.ndarray  # shape (n_years, 12)
    missing_hours: np.ndarray  # shape (n_years, 12)
    excluded: tuple[tuple[int, int], ...]  # (year, month) left out for missing data


@dataclass(frozen=True)
class Percentiles:
    p10: float | None
    median: float | None
    p90: float | None


@dataclass(frozen=True)
class MonthlyGeneration:
    capacity_kwp: float
    monthly_kwh: tuple[Percentiles, ...]  # 12, January first
    annual_kwh: Percentiles
    years_used: int  # complete years behind the annual figure
    low_confidence_months: tuple[int, ...]


def hourly_energy_per_kwp(
    gti_w_m2: np.ndarray, temp_c: np.ndarray, params: GenerationParams
) -> np.ndarray:
    """kWh produced per kWp in each hour. Missing inputs (NaN) give NaN, never a guess."""
    g = np.asarray(gti_w_m2, dtype=float)
    t = np.asarray(temp_c, dtype=float)
    if g.shape != t.shape:
        raise DomainError("invalid_series", "Irradiance and temperature series differ in length.")
    t_cell = t + (params.noct_c - 20.0) / 800.0 * g
    p_dc = (g / 1000.0) * (1.0 + params.gamma_per_c * (t_cell - 25.0))
    return np.maximum(p_dc, 0.0) * (1 - params.l_other_fraction) * (1 - params.l_shade_fraction)


def specific_yield(
    years: np.ndarray,
    months: np.ndarray,
    energy_per_kwp: np.ndarray,
    max_missing_share: float,
) -> SpecificYield:
    """Sum hourly energy into (year, month) totals.

    Missing hours (NaN or absent rows) are skipped and counted. A month missing
    more than `max_missing_share` of its hours is excluded rather than filled.
    """
    years = np.asarray(years, dtype=int)
    months = np.asarray(months, dtype=int)
    energy = np.asarray(energy_per_kwp, dtype=float)
    if not (years.shape == months.shape == energy.shape):
        raise DomainError("invalid_series", "Year, month and energy series differ in length.")
    if energy.size == 0:
        raise DomainError("invalid_series", "No hourly data.")

    year_list = tuple(int(y) for y in np.unique(years))
    totals = np.full((len(year_list), 12), np.nan)
    missing = np.zeros((len(year_list), 12), dtype=int)
    excluded: list[tuple[int, int]] = []

    for i, year in enumerate(year_list):
        for m in range(1, 13):
            sel = energy[(years == year) & (months == m)]
            expected = calendar.monthrange(year, m)[1] * 24
            present = int(np.count_nonzero(~np.isnan(sel)))
            missing[i, m - 1] = max(expected - present, 0)
            if missing[i, m - 1] / expected > max_missing_share:
                excluded.append((year, m))
                continue
            totals[i, m - 1] = float(np.nansum(sel))

    return SpecificYield(year_list, totals, missing, tuple(excluded))


def _percentiles(values: np.ndarray) -> Percentiles:
    v = values[~np.isnan(values)]
    if v.size == 0:
        return Percentiles(None, None, None)
    p10, med, p90 = np.percentile(v, [10, 50, 90])
    return Percentiles(float(p10), float(med), float(p90))


def monthly_generation(capacity_kwp: float, sy: SpecificYield) -> MonthlyGeneration:
    """Monthly and annual energy as p10 / median / p90 across the climatology years."""
    if capacity_kwp < 0:
        raise DomainError("invalid_capacity", "Capacity cannot be negative.")
    energy = capacity_kwp * sy.kwh_per_kwp
    monthly = tuple(_percentiles(energy[:, m]) for m in range(12))

    complete = ~np.isnan(energy).any(axis=1)  # only years with all 12 months
    annual = _percentiles(energy[complete].sum(axis=1)) if complete.any() else Percentiles(None, None, None)

    low_conf = tuple(sorted({m for _, m in sy.excluded}))
    return MonthlyGeneration(
        capacity_kwp=capacity_kwp,
        monthly_kwh=monthly,
        annual_kwh=annual,
        years_used=int(complete.sum()),
        low_confidence_months=low_conf,
    )


def median_annual_yield(sy: SpecificYield) -> float | None:
    """Median annual kWh per kWp over complete years; used to size against consumption."""
    return monthly_generation(1.0, sy).annual_kwh.median
