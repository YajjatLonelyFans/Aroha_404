import calendar

import numpy as np
import pytest

from app.domain.errors import DomainError
from app.domain.generation import (
    GenerationParams,
    hourly_energy_per_kwp,
    median_annual_yield,
    monthly_generation,
    specific_yield,
)

P = GenerationParams(gamma_per_c=-0.004, noct_c=45, l_other_fraction=0.14, l_shade_fraction=0.0)


def air_temp_for_cell_25(g: np.ndarray, noct: float = 45) -> np.ndarray:
    return 25 - (noct - 20) / 800 * g


def test_constant_irradiance_at_25c_has_no_temperature_term():
    g = np.full(5, 800.0)
    e = hourly_energy_per_kwp(g, air_temp_for_cell_25(g), P)
    np.testing.assert_allclose(e, 800 / 1000 * (1 - 0.14))


def test_temperature_loss_applied_once():
    g = np.array([1000.0])
    t_air = air_temp_for_cell_25(g) + 10  # cell at 35 °C
    e = hourly_energy_per_kwp(g, t_air, P)
    assert e[0] == pytest.approx(1.0 * (1 - 0.004 * 10) * (1 - 0.14))


def test_gamma_zero_removes_all_temperature_dependence():
    p = GenerationParams(gamma_per_c=0.0, noct_c=45, l_other_fraction=0.1, l_shade_fraction=0.05)
    g = np.array([200.0, 600.0, 1000.0])
    cold = hourly_energy_per_kwp(g, np.array([5.0, 5.0, 5.0]), p)
    hot = hourly_energy_per_kwp(g, np.array([45.0, 45.0, 45.0]), p)
    np.testing.assert_array_equal(cold, hot)


def test_shade_loss_multiplies_once():
    g = np.array([1000.0])
    t = air_temp_for_cell_25(g)
    base = hourly_energy_per_kwp(g, t, P)
    shaded = hourly_energy_per_kwp(g, t, GenerationParams(**{**P.__dict__, "l_shade_fraction": 0.1}))
    assert shaded[0] == pytest.approx(base[0] * 0.9)


def test_night_and_missing_hours():
    e = hourly_energy_per_kwp(np.array([0.0, np.nan]), np.array([20.0, 20.0]), P)
    assert e[0] == 0
    assert np.isnan(e[1])


def test_length_mismatch_rejected():
    with pytest.raises(DomainError):
        hourly_energy_per_kwp(np.zeros(3), np.zeros(2), P)


def _hourly(years: list[int], value: float = 0.5):
    ys, ms = [], []
    for y in years:
        for m in range(1, 13):
            n = calendar.monthrange(y, m)[1] * 24
            ys += [y] * n
            ms += [m] * n
    return np.array(ys), np.array(ms), np.full(len(ys), value)


def test_specific_yield_sums_each_month():
    years, months, e = _hourly([2023, 2024])
    sy = specific_yield(years, months, e, max_missing_share=0.05)
    assert sy.years == (2023, 2024)
    assert sy.kwh_per_kwp[0, 0] == pytest.approx(744 * 0.5)  # January
    assert sy.kwh_per_kwp[1, 1] == pytest.approx(29 * 24 * 0.5)  # Feb 2024, leap year
    assert sy.missing_hours.sum() == 0


def test_month_with_too_many_missing_hours_is_excluded():
    years, months, e = _hourly([2023, 2024])
    jan_2023 = (years == 2023) & (months == 1)
    e[np.flatnonzero(jan_2023)[:100]] = np.nan  # 100 of 744 hours ≈ 13%
    sy = specific_yield(years, months, e, max_missing_share=0.05)
    assert np.isnan(sy.kwh_per_kwp[0, 0])
    assert sy.missing_hours[0, 0] == 100
    assert sy.excluded == ((2023, 1),)


def test_few_missing_hours_are_skipped_not_filled():
    years, months, e = _hourly([2023])
    e[0] = np.nan
    sy = specific_yield(years, months, e, max_missing_share=0.05)
    assert sy.kwh_per_kwp[0, 0] == pytest.approx(743 * 0.5)
    assert sy.missing_hours[0, 0] == 1


def test_absent_rows_count_as_missing():
    years, months, e = _hourly([2023])
    keep = ~((months == 3) & (np.arange(len(e)) % 2 == 0))  # drop half of March
    sy = specific_yield(years[keep], months[keep], e[keep], max_missing_share=0.05)
    assert sy.missing_hours[0, 2] == 372
    assert (2023, 3) in sy.excluded


def test_monthly_generation_scales_with_capacity_and_orders_percentiles():
    rng = np.random.default_rng(0)  # test data only; the domain itself has no randomness
    years, months, _ = _hourly(list(range(2016, 2026)))
    e = rng.uniform(0.3, 0.7, len(years))
    sy = specific_yield(years, months, e, max_missing_share=0.05)
    one = monthly_generation(1.0, sy)
    five = monthly_generation(5.0, sy)
    for a, b in zip(one.monthly_kwh, five.monthly_kwh):
        assert b.median == pytest.approx(5 * a.median)
        assert b.p10 <= b.median <= b.p90
    assert five.annual_kwh.median == pytest.approx(5 * one.annual_kwh.median)
    assert five.years_used == 10
    assert median_annual_yield(sy) == pytest.approx(one.annual_kwh.median)


def test_annual_uses_only_complete_years():
    years, months, e = _hourly([2023, 2024])
    e[(years == 2023) & (months == 6)] = np.nan
    sy = specific_yield(years, months, e, max_missing_share=0.05)
    g = monthly_generation(2.0, sy)
    assert g.years_used == 1
    assert g.low_confidence_months == (6,)
    assert g.monthly_kwh[5].median == pytest.approx(2 * 720 * 0.5)  # only 2024 left
