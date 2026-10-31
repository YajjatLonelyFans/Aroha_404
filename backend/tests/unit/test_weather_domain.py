from datetime import date

import numpy as np
import pytest

from app.domain.weather import (
    ForecastDay,
    OutlookRule,
    aggregate_climatology,
    classify_day,
    climatology_period,
    daily_forecast,
    split_times,
)
from tests.weather_data import hourly_body


def test_period_is_last_complete_years():
    assert climatology_period(date(2026, 11, 1), 10) == (date(2016, 1, 1), date(2025, 12, 31))


def test_period_in_early_january_steps_back_a_year():
    assert climatology_period(date(2026, 1, 3), 10) == (date(2015, 1, 1), date(2024, 12, 31))


def test_split_times():
    years, months = split_times(["2024-02-29T23:00", "2025-12-01T00:00"])
    assert years.tolist() == [2024, 2025]
    assert months.tolist() == [2, 12]


def _aggregate(body: dict, max_missing: float = 0.05):
    h = body["hourly"]
    years, months = split_times(h["time"])
    arr = {k: np.array(v, dtype=float) for k, v in h.items() if k != "time"}
    return aggregate_climatology(
        years, months, gti_w_m2=arr["global_tilted_irradiance"], temp_c=arr["temperature_2m"],
        cloud_cover_pct=arr["cloud_cover"], precip_mm=arr["precipitation"],
        sunshine_s=arr["sunshine_duration"], max_missing_share=max_missing,
    )


def test_climatology_monthly_totals_and_means():
    clim = _aggregate(hourly_body(date(2023, 1, 1), date(2024, 12, 31)))
    jan = clim.months[0]
    assert clim.years == (2023, 2024)
    assert jan.gti_kwh_m2.median == pytest.approx(31 * 12 * 0.5)  # 12 sunny hours at 0.5 kW/m²
    assert jan.temp_mean_c == pytest.approx(25)
    assert jan.cloud_cover_pct == pytest.approx(30)
    assert jan.precip_mm == pytest.approx(31 * 24 * 0.1)
    assert jan.sunshine_h == pytest.approx(31 * 24 * 0.5)
    assert clim.months[1].per_year_gti_kwh_m2 == pytest.approx((28 * 6.0, 29 * 6.0))
    assert clim.missing_hours == 0 and clim.missing_fields == ()


def test_variable_with_no_data_is_reported_missing():
    body = hourly_body(date(2024, 1, 1), date(2024, 12, 31))
    body["hourly"]["cloud_cover"] = [None] * len(body["hourly"]["time"])
    clim = _aggregate(body)
    assert clim.missing_fields == ("cloud_cover_pct",)
    assert clim.months[0].cloud_cover_pct is None
    assert clim.months[0].gti_kwh_m2.median is not None


def test_daily_forecast_sums_and_extremes():
    body = hourly_body(date(2026, 11, 1), date(2026, 11, 2), gti_day=400)
    h = body["hourly"]
    h["temperature_2m"][14] = 31.0
    days = daily_forecast(h["time"], np.array(h["global_tilted_irradiance"]), np.array(h["cloud_cover"]),
                          np.array(h["precipitation"]), np.array(h["temperature_2m"]))
    assert [d.date for d in days] == ["2026-11-01", "2026-11-02"]
    assert days[0].gti_kwh_m2 == pytest.approx(12 * 0.4)
    assert days[0].temp_max_c == 31.0 and days[0].temp_min_c == 25.0
    assert days[0].precip_mm == pytest.approx(2.4)


def test_incomplete_day_is_not_summarised():
    body = hourly_body(date(2026, 11, 1), date(2026, 11, 1))
    h = body["hourly"]
    h["global_tilted_irradiance"][12] = None
    days = daily_forecast(h["time"], np.array(h["global_tilted_irradiance"], dtype=float),
                          np.array(h["cloud_cover"]), np.array(h["precipitation"]), np.array(h["temperature_2m"]))
    assert days[0].gti_kwh_m2 is None


RULE = OutlookRule(sunny_min_ratio=0.9, cloudy_max_ratio=0.5, rain_min_mm=5)


def _day(gti, rain=0.0):
    return ForecastDay("2026-11-05", gti, 20, rain, 28, 15)


@pytest.mark.parametrize(
    "gti, rain, expected",
    [(5.0, 0, "sunny"), (3.0, 0, "mixed"), (2.0, 0, "cloudy"), (5.0, 8, "rain"), (None, 0, None)],
)
def test_classify_day(gti, rain, expected):
    # November typical day: 150 kWh/m² ÷ 30 days = 5 kWh/m².
    assert classify_day(_day(gti, rain), 150.0, RULE) == expected


def test_classify_needs_climatology():
    assert classify_day(_day(5.0), None, RULE) is None
