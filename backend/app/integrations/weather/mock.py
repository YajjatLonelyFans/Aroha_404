"""Mock weather provider for offline development. Every result has is_mock=True.

History replays one recorded year (2024, central Delhi, tilt 20°, south) for
every requested year, so all years are identical: ranges collapse to a single
value. Current and forecast replay recorded responses with dates moved to today.
"""

import gzip
import json
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from app.core.settings import BACKEND_DIR
from app.integrations.weather.base import (
    CURRENT_VARS,
    FORECAST_VARS,
    HISTORY_VARS,
    CurrentConditions,
    HourlySeries,
    SourceInfo,
)

FIXTURES = BACKEND_DIR / "tests" / "fixtures"
MOCK_NAME = "Mock weather (recorded Open-Meteo data, not live)"


@lru_cache
def _load(name: str) -> dict[str, Any]:
    path = FIXTURES / name
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _source() -> SourceInfo:
    return SourceInfo(name=MOCK_NAME, url="mock://weather", retrieved_at=datetime.now(timezone.utc), is_mock=True)


class MockWeatherProvider:
    is_mock = True

    async def hourly_history(
        self, lat: float, lon: float, tilt: float, azimuth: float, start: date, end: date
    ) -> HourlySeries:
        body = _load("open_meteo_archive_2024.json.gz")
        hourly = body["hourly"]
        by_slot = {t[5:]: i for i, t in enumerate(hourly["time"])}  # "MM-DDTHH:MM" → index

        times: list[str] = []
        values: dict[str, list[float | None]] = {n: [] for n in HISTORY_VARS}
        day = start
        while day <= end:
            for hour in range(24):
                stamp = f"{day.isoformat()}T{hour:02d}:00"
                i = by_slot[stamp[5:]]
                times.append(stamp)
                for n in HISTORY_VARS:
                    values[n].append(hourly[n][i])
            day += timedelta(days=1)
        return HourlySeries(times, values, body["hourly_units"], _source())

    async def current(self, lat: float, lon: float) -> CurrentConditions:
        body = _load("open_meteo_current.json")
        return CurrentConditions(
            time=body["current"]["time"],
            values={n: body["current"].get(n) for n in CURRENT_VARS},
            units=body["current_units"],
            source=_source(),
        )

    async def forecast(
        self, lat: float, lon: float, tilt: float, azimuth: float, days: int = 7
    ) -> HourlySeries:
        body = _load("open_meteo_forecast.json")
        hourly = body["hourly"]
        first = date.fromisoformat(hourly["time"][0][:10])
        shift = date.today() - first
        times = [
            (date.fromisoformat(t[:10]) + shift).isoformat() + t[10:]
            for t in hourly["time"][: days * 24]
        ]
        values = {n: list(hourly[n][: days * 24]) for n in FORECAST_VARS}
        return HourlySeries(times, values, body["hourly_units"], _source())
