"""Season buckets and seasonal notes derived from the climatology.

Notes are produced by fixed rules over the data; each one lists the fields
and values it is based on. No claim about Delhi is hardcoded here.
"""

from dataclasses import dataclass

from app.domain.errors import DomainError
from app.domain.units import month_name


@dataclass(frozen=True)
class MonthClimate:
    month: int
    gti_kwh_m2: float | None  # median across years
    temp_mean_c: float | None
    cloud_cover_pct: float | None
    precip_mm: float | None
    sunshine_h: float | None


@dataclass(frozen=True)
class SeasonNote:
    season: str
    statement: str
    evidence_fields: tuple[str, ...]
    values: dict[str, float]


def season_of(month: int, seasons: dict[str, list[int]]) -> str:
    for name, months in seasons.items():
        if month in months:
            return name
    raise DomainError("invalid_month", f"Month {month} is not in any season.")


def _label(season: str) -> str:
    return season.replace("_", "-")


def _with(months: list[MonthClimate], field: str) -> list[MonthClimate]:
    return [m for m in months if getattr(m, field) is not None]


def season_notes(months: list[MonthClimate], seasons: dict[str, list[int]]) -> list[SeasonNote]:
    notes: list[SeasonNote] = []

    sunny = _with(months, "gti_kwh_m2")
    if sunny:
        peak = max(sunny, key=lambda m: (m.gti_kwh_m2, -m.month))
        low = min(sunny, key=lambda m: (m.gti_kwh_m2, m.month))
        notes.append(SeasonNote(
            season_of(peak.month, seasons),
            f"{month_name(peak.month)} gets the most sunlight on the panels: "
            f"{peak.gti_kwh_m2:.1f} kWh/m² in a typical year.",
            ("gti_kwh_m2",),
            {"month": peak.month, "gti_kwh_m2": round(peak.gti_kwh_m2, 1)},
        ))
        notes.append(SeasonNote(
            season_of(low.month, seasons),
            f"{month_name(low.month)} gets the least: {low.gti_kwh_m2:.1f} kWh/m².",
            ("gti_kwh_m2",),
            {"month": low.month, "gti_kwh_m2": round(low.gti_kwh_m2, 1)},
        ))

        overall = sum(m.gti_kwh_m2 for m in sunny) / len(sunny)
        for season, season_months in seasons.items():
            in_season = [m for m in sunny if m.month in season_months]
            if not in_season or overall == 0:
                continue
            avg = sum(m.gti_kwh_m2 for m in in_season) / len(in_season)
            diff = 100 * (avg - overall) / overall
            direction = "above" if diff >= 0 else "below"
            notes.append(SeasonNote(
                season,
                f"{_label(season).capitalize()} months average {avg:.1f} kWh/m² of sunlight, "
                f"{abs(diff):.0f}% {direction} the yearly monthly average of {overall:.1f}.",
                ("gti_kwh_m2",),
                {"season_gti_kwh_m2": round(avg, 1), "year_avg_gti_kwh_m2": round(overall, 1),
                 "diff_pct": round(diff)},
            ))

    wet = _with(months, "precip_mm")
    if wet:
        m = max(wet, key=lambda x: (x.precip_mm, -x.month))
        values = {"month": m.month, "precip_mm": round(m.precip_mm, 1)}
        statement = f"{month_name(m.month)} is the wettest month, with {m.precip_mm:.0f} mm of rain"
        fields: tuple[str, ...] = ("precip_mm",)
        if m.cloud_cover_pct is not None:
            statement += f" and {m.cloud_cover_pct:.0f}% average cloud cover"
            values["cloud_cover_pct"] = round(m.cloud_cover_pct)
            fields += ("cloud_cover_pct",)
        notes.append(SeasonNote(season_of(m.month, seasons), statement + ".", fields, values))

    warm = _with(months, "temp_mean_c")
    if warm:
        m = max(warm, key=lambda x: (x.temp_mean_c, -x.month))
        notes.append(SeasonNote(
            season_of(m.month, seasons),
            f"{month_name(m.month)} is the hottest month (mean {m.temp_mean_c:.1f} °C). "
            "Heat lowers panel efficiency; the estimate accounts for it hour by hour.",
            ("temp_mean_c",),
            {"month": m.month, "temp_mean_c": round(m.temp_mean_c, 1)},
        ))

    return notes
