"""Climatology aggregation and the short-term outlook.

The climatology (10 years of history) feeds every long-term number. The
forecast only labels the next few days and never feeds annual or money figures.
"""

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np

from app.domain.generation import Percentiles
from app.domain.series import by_year_month

Outlook = Literal["sunny", "mixed", "cloudy", "rain"]


def climatology_period(today: date, years: int) -> tuple[date, date]:
    """The last `years` complete calendar years. ERA5 lags about 5 days, so early
    January still uses the year before last as the final year."""
    last = today.year - 1 if today >= date(today.year, 1, 10) else today.year - 2
    return date(last - years + 1, 1, 1), date(last, 12, 31)


def split_times(times: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """ISO local times ('2024-06-01T13:00') → year and month arrays."""
    years = np.fromiter((int(t[:4]) for t in times), dtype=int, count=len(times))
    months = np.fromiter((int(t[5:7]) for t in times), dtype=int, count=len(times))
    return years, months


@dataclass(frozen=True)
class MonthStats:
    month: int
    gti_kwh_m2: Percentiles  # across years
    per_year_gti_kwh_m2: tuple[float | None, ...]
    temp_mean_c: float | None
    cloud_cover_pct: float | None
    precip_mm: float | None  # typical monthly total (mean across years)
    sunshine_h: float | None  # typical monthly total (mean across years)
    missing_hours: int


@dataclass(frozen=True)
class Climatology:
    years: tuple[int, ...]
    months: tuple[MonthStats, ...]
    missing_fields: tuple[str, ...]  # variables with no data at all
    missing_hours: int
    excluded: tuple[tuple[int, int], ...]  # (year, month) GTI cells left out


def _mean_or_none(values: np.ndarray) -> float | None:
    v = values[~np.isnan(values)]
    return float(v.mean()) if v.size else None


def _pct(values: np.ndarray) -> Percentiles:
    v = values[~np.isnan(values)]
    if v.size == 0:
        return Percentiles(None, None, None)
    p10, med, p90 = np.percentile(v, [10, 50, 90])
    return Percentiles(float(p10), float(med), float(p90))


def aggregate_climatology(
    years: np.ndarray,
    months: np.ndarray,
    *,
    gti_w_m2: np.ndarray,
    temp_c: np.ndarray,
    cloud_cover_pct: np.ndarray,
    precip_mm: np.ndarray,
    sunshine_s: np.ndarray,
    max_missing_share: float,
) -> Climatology:
    gti = by_year_month(years, months, np.asarray(gti_w_m2, float) / 1000.0, max_missing_share, "sum")
    temp = by_year_month(years, months, temp_c, max_missing_share, "mean")
    cloud = by_year_month(years, months, cloud_cover_pct, max_missing_share, "mean")
    rain = by_year_month(years, months, precip_mm, max_missing_share, "sum")
    sun = by_year_month(years, months, np.asarray(sunshine_s, float) / 3600.0, max_missing_share, "sum")

    named = {"gti_kwh_m2": gti, "temp_mean_c": temp, "cloud_cover_pct": cloud,
             "precip_mm": rain, "sunshine_h": sun}
    missing_fields = tuple(k for k, t in named.items() if np.isnan(t.values).all())

    stats = tuple(
        MonthStats(
            month=m + 1,
            gti_kwh_m2=_pct(gti.values[:, m]),
            per_year_gti_kwh_m2=tuple(None if np.isnan(v) else float(v) for v in gti.values[:, m]),
            temp_mean_c=_mean_or_none(temp.values[:, m]),
            cloud_cover_pct=_mean_or_none(cloud.values[:, m]),
            precip_mm=_mean_or_none(rain.values[:, m]),
            sunshine_h=_mean_or_none(sun.values[:, m]),
            missing_hours=int(gti.missing_hours[:, m].sum()),
        )
        for m in range(12)
    )
    return Climatology(
        years=gti.years,
        months=stats,
        missing_fields=missing_fields,
        missing_hours=int(gti.missing_hours.sum()),
        excluded=gti.excluded,
    )


# --- Short-term outlook ------------------------------------------------------------------


@dataclass(frozen=True)
class OutlookRule:
    sunny_min_ratio: float  # day GTI ÷ typical day GTI for the month
    cloudy_max_ratio: float
    rain_min_mm: float


@dataclass(frozen=True)
class ForecastDay:
    date: str
    gti_kwh_m2: float | None
    cloud_cover_pct: float | None
    precip_mm: float | None
    temp_max_c: float | None
    temp_min_c: float | None
    outlook: Outlook | None = None


def _day_value(values: np.ndarray, how: str) -> float | None:
    if values.size == 0 or np.isnan(values).any():
        return None  # an incomplete day is not summarised
    return float({"sum": values.sum, "mean": values.mean, "max": values.max, "min": values.min}[how]())


def daily_forecast(
    times: list[str],
    gti_w_m2: np.ndarray,
    cloud_cover_pct: np.ndarray,
    precip_mm: np.ndarray,
    temp_c: np.ndarray,
) -> list[ForecastDay]:
    days = np.array([t[:10] for t in times])
    gti = np.asarray(gti_w_m2, float)
    cloud = np.asarray(cloud_cover_pct, float)
    rain = np.asarray(precip_mm, float)
    temp = np.asarray(temp_c, float)
    out: list[ForecastDay] = []
    for day in dict.fromkeys(days):  # keeps order
        sel = days == day
        g = _day_value(gti[sel], "sum")
        out.append(ForecastDay(
            date=str(day),
            gti_kwh_m2=None if g is None else g / 1000.0,
            cloud_cover_pct=_day_value(cloud[sel], "mean"),
            precip_mm=_day_value(rain[sel], "sum"),
            temp_max_c=_day_value(temp[sel], "max"),
            temp_min_c=_day_value(temp[sel], "min"),
        ))
    return out


def classify_day(
    day: ForecastDay, month_median_gti_kwh_m2: float | None, rule: OutlookRule
) -> Outlook | None:
    """Label a forecast day against what is typical for its month in the climatology."""
    if day.precip_mm is not None and day.precip_mm >= rule.rain_min_mm:
        return "rain"
    if day.gti_kwh_m2 is None or not month_median_gti_kwh_m2:
        return None
    y, m = int(day.date[:4]), int(day.date[5:7])
    typical_day = month_median_gti_kwh_m2 / calendar.monthrange(y, m)[1]
    ratio = day.gti_kwh_m2 / typical_day
    if ratio >= rule.sunny_min_ratio:
        return "sunny"
    if ratio < rule.cloudy_max_ratio:
        return "cloudy"
    return "mixed"
