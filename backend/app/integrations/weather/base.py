"""Weather provider interface. Values stay `None` when the provider has no data."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from app.core.errors import AppError

HISTORY_VARS = ("global_tilted_irradiance", "temperature_2m", "cloud_cover", "precipitation", "sunshine_duration")
FORECAST_VARS = ("global_tilted_irradiance", "cloud_cover", "precipitation", "temperature_2m")
CURRENT_VARS = ("temperature_2m", "relative_humidity_2m", "precipitation", "cloud_cover", "wind_speed_10m", "is_day")


@dataclass(frozen=True)
class SourceInfo:
    name: str
    url: str
    retrieved_at: datetime
    is_mock: bool = False


@dataclass(frozen=True)
class HourlySeries:
    """Hourly values keyed by Open-Meteo variable name; times are local (Asia/Kolkata)."""

    times: list[str]
    values: dict[str, list[float | None]]
    units: dict[str, str]
    source: SourceInfo


@dataclass(frozen=True)
class CurrentConditions:
    time: str
    values: dict[str, Any]
    units: dict[str, str]
    source: SourceInfo


class WeatherUnavailable(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("weather_unavailable", message, status_code=503, retryable=True)


class WeatherRequestRejected(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("weather_request_rejected", message, status_code=502)


class WeatherProvider(Protocol):
    is_mock: bool

    async def hourly_history(
        self, lat: float, lon: float, tilt: float, azimuth: float, start: date, end: date
    ) -> HourlySeries: ...

    async def current(self, lat: float, lon: float) -> CurrentConditions: ...

    async def forecast(
        self, lat: float, lon: float, tilt: float, azimuth: float, days: int = 7
    ) -> HourlySeries: ...
