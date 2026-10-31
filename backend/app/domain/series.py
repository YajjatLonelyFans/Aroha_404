"""Grouping hourly series into (year, month) cells with a missing-data rule."""

import calendar
from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.domain.errors import DomainError


@dataclass(frozen=True)
class YearMonthTable:
    years: tuple[int, ...]
    values: np.ndarray  # shape (n_years, 12); NaN where excluded
    missing_hours: np.ndarray  # shape (n_years, 12)
    excluded: tuple[tuple[int, int], ...]  # (year, month) with too much missing data


def by_year_month(
    years: np.ndarray,
    months: np.ndarray,
    values: np.ndarray,
    max_missing_share: float,
    how: Literal["sum", "mean"] = "sum",
) -> YearMonthTable:
    """Reduce hourly values per (year, month).

    Missing hours (NaN or absent rows) are skipped and counted against the
    calendar. A month missing more than `max_missing_share` is excluded (NaN),
    never filled.
    """
    years = np.asarray(years, dtype=int)
    months = np.asarray(months, dtype=int)
    values = np.asarray(values, dtype=float)
    if not (years.shape == months.shape == values.shape):
        raise DomainError("invalid_series", "Year, month and value series differ in length.")
    if values.size == 0:
        raise DomainError("invalid_series", "No hourly data.")

    year_list = tuple(int(y) for y in np.unique(years))
    out = np.full((len(year_list), 12), np.nan)
    missing = np.zeros((len(year_list), 12), dtype=int)
    excluded: list[tuple[int, int]] = []

    for i, year in enumerate(year_list):
        in_year = years == year
        for m in range(1, 13):
            sel = values[in_year & (months == m)]
            expected = calendar.monthrange(year, m)[1] * 24
            present = sel[~np.isnan(sel)]
            missing[i, m - 1] = max(expected - present.size, 0)
            if missing[i, m - 1] / expected > max_missing_share:
                excluded.append((year, m))
                continue
            out[i, m - 1] = float(present.sum() if how == "sum" else present.mean())

    return YearMonthTable(year_list, out, missing, tuple(excluded))
