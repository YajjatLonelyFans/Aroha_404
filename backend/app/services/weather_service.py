"""Weather service: climatology, current conditions and the short-term outlook.

Climatology (10 years of hourly history) is aggregated once per grid cell,
tilt and azimuth, then cached with provenance. Raw hourly rows are not stored;
monthly aggregates and per-year specific yield (kWh per kWp) are.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from app.core.assumptions import AssumptionMissingError, Assumptions
from app.core.errors import AppError
from app.db.weather_repo import WeatherRepo
from app.domain.errors import DomainError
from app.domain.generation import (
    GenerationParams,
    Percentiles,
    SpecificYield,
    hourly_energy_per_kwp,
    monthly_generation,
    specific_yield,
)
from app.domain.seasons import MonthClimate, season_notes
from app.domain.weather import (
    ForecastDay,
    OutlookRule,
    aggregate_climatology,
    classify_day,
    climatology_period,
    daily_forecast,
    split_times,
)
from app.integrations.weather.base import SourceInfo, WeatherProvider
from app.schemas.common import Source
from app.schemas.weather import (
    ClimatologyMonth,
    ClimatologyResponse,
    CurrentObservation,
    CurrentResponse,
    ForecastDayOut,
    ForecastResponse,
    MissingData,
    PercentilesOut,
    SeasonNoteOut,
    SpecificYieldOut,
)

log = logging.getLogger(__name__)

MODEL_VERSION = "climatology-1.0.0"
CURRENT_TTL = timedelta(hours=1)
FORECAST_TTL = timedelta(hours=6)
FORECAST_DAYS = 7
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"

CLIMATOLOGY_UNITS = {
    "gti_kwh_m2": "kWh/m² per month (plane of array)",
    "temp_mean_c": "°C",
    "cloud_cover_pct": "%",
    "precip_mm": "mm per month",
    "sunshine_h": "hours per month",
    "specific_yield": "kWh per kWp",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def grid_key(lat: float, lon: float) -> tuple[float, float, str]:
    """Round to 2 dp (~1 km); ERA5 itself is ~25 km, so nearby roofs share a cache entry."""
    lat_r, lon_r = round(lat, 2), round(lon, 2)
    return lat_r, lon_r, f"{lat_r:.2f}_{lon_r:.2f}"


def _r(value: float | None, ndigits: int) -> float | None:
    return None if value is None else round(value, ndigits)


def _pct_out(p: Percentiles | dict[str, Any], ndigits: int = 1) -> PercentilesOut:
    if isinstance(p, dict):
        p = Percentiles(p.get("p10"), p.get("median"), p.get("p90"))
    return PercentilesOut(p10=_r(p.p10, ndigits), median=_r(p.median, ndigits), p90=_r(p.p90, ndigits))


def _nan_to_none(values: np.ndarray) -> list[float | None]:
    return [None if np.isnan(v) else float(v) for v in values]


def _source_doc(src: SourceInfo) -> dict[str, Any]:
    return {"name": src.name, "url": src.url, "retrieved_at": src.retrieved_at}


def _source_out(doc: dict[str, Any]) -> Source:
    s = doc["source"]
    return Source(name=s["name"], url=s.get("url"), retrieved_at=s["retrieved_at"], note=ATTRIBUTION)


def specific_yield_from_doc(doc: dict[str, Any]) -> SpecificYield | None:
    """Rebuild the per-year specific yield stored in a climatology document."""
    rows = [m.get("yield_kwh_per_kwp_per_year") for m in doc["monthly"]]
    if any(r is None for r in rows):
        return None
    years = tuple(doc["years"])
    table = np.array([[np.nan if v is None else v for v in r] for r in rows], dtype=float).T
    excluded = tuple(
        (years[i], m + 1) for m in range(12) for i in range(len(years)) if np.isnan(table[i, m])
    )
    return SpecificYield(years, table, np.zeros_like(table, dtype=int), excluded)


class WeatherService:
    def __init__(
        self,
        provider: WeatherProvider,
        repo: WeatherRepo,
        assumptions: Assumptions,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._provider = provider
        self._repo = repo
        self._a = assumptions
        self._clock = clock

    # --- helpers -------------------------------------------------------------------------

    def _check_location(self, lat: float, lon: float) -> None:
        min_lon, min_lat, max_lon, max_lat = self._a.validation.delhi_bbox
        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            raise DomainError("outside_delhi", "The location must be inside Delhi.")

    def _yield_params(self) -> dict[str, Any] | None:
        """Module and loss values needed for specific yield, or None until they are filled in."""
        try:
            return {
                "gamma_per_c": self._a.require("module.gamma_per_c"),
                "noct_c": self._a.require("module.noct_c"),
                "l_other_fraction": self._a.require("losses.l_other_fraction"),
                "assumptions_version": self._a.version,
            }
        except AssumptionMissingError:
            return None

    def _outlook_rule(self) -> OutlookRule | None:
        try:
            return OutlookRule(
                sunny_min_ratio=self._a.require("forecast.sunny_min_ratio"),
                cloudy_max_ratio=self._a.require("forecast.cloudy_max_ratio"),
                rain_min_mm=self._a.require("forecast.rain_min_mm"),
            )
        except AssumptionMissingError:
            return None

    def _period(self) -> tuple[Any, Any, str]:
        start, end = climatology_period(self._clock().date(), self._a.climatology.years)
        return start, end, f"{start.year}-{end.year}"

    # --- climatology ---------------------------------------------------------------------

    async def climatology_doc(
        self, lat: float, lon: float, tilt: float, azimuth: float
    ) -> tuple[dict[str, Any], bool, list[str]]:
        """(document, served_from_cache, notes). Fetches and caches on a miss."""
        self._check_location(lat, lon)
        lat_r, lon_r, gk = grid_key(lat, lon)
        tilt_r, az_r = float(round(tilt)), float(round(azimuth))
        start, end, period = self._period()
        key = {"grid_key": gk, "tilt_deg": tilt_r, "azimuth_deg": az_r, "period": period}
        params = self._yield_params()

        cached = await self._repo.find_climatology(key)
        if (
            cached is not None
            and cached.get("is_mock") == self._provider.is_mock
            and cached.get("yield_params") == params
        ):
            return cached, True, []

        try:
            series = await self._provider.hourly_history(lat_r, lon_r, tilt_r, az_r, start, end)
        except AppError:
            if cached is not None:
                log.warning("Serving cached climatology for %s after a failed refresh", gk)
                return cached, True, ["Live refresh failed; showing the copy saved earlier."]
            raise

        doc = self._build_climatology(series, key, lat_r, lon_r, params)
        doc["_id"] = await self._repo.save_climatology(key, doc) or None
        return doc, False, []

    def _build_climatology(
        self, series: Any, key: dict[str, Any], lat: float, lon: float, params: dict[str, Any] | None
    ) -> dict[str, Any]:
        if not series.times:
            raise AppError("weather_empty", "The weather service returned no data.", status_code=502)
        v = {n: np.array(series.values[n], dtype=float) for n in series.values}
        years, months = split_times(series.times)
        max_missing = self._a.climatology.max_missing_share

        clim = aggregate_climatology(
            years, months,
            gti_w_m2=v["global_tilted_irradiance"], temp_c=v["temperature_2m"],
            cloud_cover_pct=v["cloud_cover"], precip_mm=v["precipitation"],
            sunshine_s=v["sunshine_duration"], max_missing_share=max_missing,
        )

        yield_rows: list[list[float | None] | None] = [None] * 12
        if params is not None:
            energy = hourly_energy_per_kwp(
                v["global_tilted_irradiance"], v["temperature_2m"],
                GenerationParams(params["gamma_per_c"], params["noct_c"], params["l_other_fraction"], 0.0),
            )
            sy = specific_yield(years, months, energy, max_missing)
            yield_rows = [_nan_to_none(sy.kwh_per_kwp[:, m]) for m in range(12)]

        return {
            **key,
            "kind": "climatology",
            "lat": lat,
            "lon": lon,
            "years": list(clim.years),
            "monthly": [
                {
                    "month": s.month,
                    "gti_kwh_m2": {"p10": s.gti_kwh_m2.p10, "median": s.gti_kwh_m2.median, "p90": s.gti_kwh_m2.p90},
                    "per_year_gti_kwh_m2": list(s.per_year_gti_kwh_m2),
                    "temp_mean_c": s.temp_mean_c,
                    "cloud_cover_pct": s.cloud_cover_pct,
                    "precip_mm": s.precip_mm,
                    "sunshine_h": s.sunshine_h,
                    "missing_hours": s.missing_hours,
                    "yield_kwh_per_kwp_per_year": yield_rows[s.month - 1],
                }
                for s in clim.months
            ],
            "yield_params": params,
            "units": CLIMATOLOGY_UNITS,
            "source": _source_doc(series.source),
            "is_mock": series.source.is_mock,
            "missing": {
                "fields": list(clim.missing_fields),
                "hours": clim.missing_hours,
                "excluded": [list(e) for e in clim.excluded],
            },
            "expires_at": None,
            "model_version": MODEL_VERSION,
            "created_at": self._clock(),
        }

    async def climatology(self, lat: float, lon: float, tilt: float, azimuth: float) -> ClimatologyResponse:
        doc, cached, notes = await self.climatology_doc(lat, lon, tilt, azimuth)

        months = [
            MonthClimate(
                month=m["month"], gti_kwh_m2=m["gti_kwh_m2"]["median"], temp_mean_c=m["temp_mean_c"],
                cloud_cover_pct=m["cloud_cover_pct"], precip_mm=m["precip_mm"], sunshine_h=m["sunshine_h"],
            )
            for m in doc["monthly"]
        ]
        notes_out = [
            SeasonNoteOut(season=n.season, statement=n.statement,
                          evidence_fields=list(n.evidence_fields), values=n.values)
            for n in season_notes(months, self._a.seasons)
        ]

        sy = specific_yield_from_doc(doc)
        yield_out = None
        if sy is None:
            notes.append(
                "Energy per kWp is not available yet: set module.gamma_per_c, module.noct_c and "
                "losses.l_other_fraction in the assumptions file."
            )
        else:
            per_kwp = monthly_generation(1.0, sy)
            yield_out = SpecificYieldOut(
                monthly_kwh_per_kwp=[_pct_out(p) for p in per_kwp.monthly_kwh],
                annual_kwh_per_kwp=_pct_out(per_kwp.annual_kwh, 0),
                years_used=per_kwp.years_used,
                low_confidence_months=list(per_kwp.low_confidence_months),
            )
        if doc.get("is_mock"):
            notes.append("Mock weather: recorded data, not a live retrieval.")

        max_missing_pct = round(100 * self._a.climatology.max_missing_share)
        return ClimatologyResponse(
            climatology_id=str(doc.get("_id") or ""),
            grid_key=doc["grid_key"],
            lat=doc["lat"],
            lon=doc["lon"],
            tilt_deg=doc["tilt_deg"],
            azimuth_deg=doc["azimuth_deg"],
            period=doc["period"],
            years=doc["years"],
            monthly=[
                ClimatologyMonth(
                    month=m["month"],
                    gti_kwh_m2=_pct_out(m["gti_kwh_m2"]),
                    temp_mean_c=_r(m["temp_mean_c"], 1),
                    cloud_cover_pct=_r(m["cloud_cover_pct"], 0),
                    precip_mm=_r(m["precip_mm"], 1),
                    sunshine_h=_r(m["sunshine_h"], 1),
                    missing_hours=m["missing_hours"],
                )
                for m in doc["monthly"]
            ],
            season_notes=notes_out,
            specific_yield=yield_out,
            units=doc["units"],
            assumptions=[
                f"Long-term figures use hourly history for {doc['period']} from the ERA5 reanalysis "
                "(about 25 km grid): it reflects regional cloud and haze, not shade on one roof.",
                "Sunlight on the panels assumes 20% ground reflectance and an even sky (Open-Meteo method).",
                "Energy per kWp excludes roof shading, which is applied per roof.",
                f"Months missing more than {max_missing_pct}% of their hours are left out of the range.",
            ],
            notes=notes,
            missing=MissingData(
                fields=doc["missing"]["fields"],
                hours=doc["missing"]["hours"],
                excluded_months=[tuple(e) for e in doc["missing"]["excluded"]],
            ),
            sources=[_source_out(doc)],
            retrieved_at=doc["source"]["retrieved_at"],
            cached=cached,
            is_mock=bool(doc.get("is_mock")),
        )

    # --- current conditions --------------------------------------------------------------

    async def current(self, lat: float, lon: float) -> CurrentResponse:
        self._check_location(lat, lon)
        lat_r, lon_r, gk = grid_key(lat, lon)
        key = {"grid_key": gk}
        now = self._clock()

        doc = await self._repo.find_current(key, now)
        cached = doc is not None and doc.get("is_mock") == self._provider.is_mock
        if not cached:
            cur = await self._provider.current(lat_r, lon_r)
            v = cur.values
            doc = {
                **key,
                "kind": "current",
                "observation": {
                    "time": cur.time,
                    "temperature_c": v.get("temperature_2m"),
                    "relative_humidity_pct": v.get("relative_humidity_2m"),
                    "precipitation_mm": v.get("precipitation"),
                    "cloud_cover_pct": v.get("cloud_cover"),
                    "wind_speed_kmh": v.get("wind_speed_10m"),
                    "is_day": None if v.get("is_day") is None else bool(v["is_day"]),
                },
                "units": cur.units,
                "source": _source_doc(cur.source),
                "is_mock": cur.source.is_mock,
                "expires_at": now + CURRENT_TTL,
            }
            await self._repo.save_current(key, doc)

        return CurrentResponse(
            grid_key=gk,
            observation=CurrentObservation(**doc["observation"]),
            sources=[_source_out(doc)],
            retrieved_at=doc["source"]["retrieved_at"],
            cached=cached,
            is_mock=bool(doc.get("is_mock")),
        )

    # --- short-term outlook --------------------------------------------------------------

    async def forecast(self, lat: float, lon: float, tilt: float, azimuth: float) -> ForecastResponse:
        self._check_location(lat, lon)
        lat_r, lon_r, gk = grid_key(lat, lon)
        tilt_r, az_r = float(round(tilt)), float(round(azimuth))
        key = {"grid_key": gk, "tilt_deg": tilt_r, "azimuth_deg": az_r}
        now = self._clock()

        doc = await self._repo.find_forecast(key, now)
        cached = doc is not None and doc.get("is_mock") == self._provider.is_mock
        if not cached:
            series = await self._provider.forecast(lat_r, lon_r, tilt_r, az_r, FORECAST_DAYS)
            v = {n: np.array(series.values[n], dtype=float) for n in series.values}
            days = daily_forecast(
                series.times, v["global_tilted_irradiance"], v["cloud_cover"],
                v["precipitation"], v["temperature_2m"],
            )
            doc = {
                **key,
                "horizon_days": FORECAST_DAYS,
                "daily": [d.__dict__ for d in days],
                "source": _source_doc(series.source),
                "is_mock": series.source.is_mock,
                "retrieved_at": series.source.retrieved_at,
                "expires_at": now + FORECAST_TTL,
            }
            await self._repo.save_forecast(key, doc)

        # Labels are worked out on every read, so newly filled rules apply at once.
        notes = ["For the next few days only. Never used in yearly or savings estimates."]
        rule = self._outlook_rule()
        _, _, period = self._period()
        clim = await self._repo.find_climatology({**key, "period": period})
        medians = {m["month"]: m["gti_kwh_m2"]["median"] for m in clim["monthly"]} if clim else {}
        if rule is None:
            notes.append("Day labels are off until the forecast thresholds are set in the assumptions file.")
        elif not medians:
            notes.append("Day labels need the long-term data for this spot; load the climatology first.")

        daily_out = []
        for d in doc["daily"]:
            day = ForecastDay(**{k: d.get(k) for k in ForecastDay.__dataclass_fields__})
            outlook = None
            if rule is not None and medians:
                outlook = classify_day(day, medians.get(int(day.date[5:7])), rule)
            daily_out.append(ForecastDayOut(
                date=day.date,
                gti_kwh_m2=_r(day.gti_kwh_m2, 2),
                cloud_cover_pct=_r(day.cloud_cover_pct, 0),
                precip_mm=_r(day.precip_mm, 1),
                temp_max_c=_r(day.temp_max_c, 1),
                temp_min_c=_r(day.temp_min_c, 1),
                outlook=outlook,
            ))
        if doc.get("is_mock"):
            notes.append("Mock weather: recorded data, not a live forecast.")

        return ForecastResponse(
            grid_key=gk,
            tilt_deg=tilt_r,
            azimuth_deg=az_r,
            horizon_days=doc["horizon_days"],
            daily=daily_out,
            notes=notes,
            sources=[_source_out(doc)],
            retrieved_at=doc["source"]["retrieved_at"],
            cached=cached,
            is_mock=bool(doc.get("is_mock")),
        )
