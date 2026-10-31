"""Open-Meteo adapter: Historical Weather API (ERA5) and Forecast API.

Docs: https://open-meteo.com/en/docs/historical-weather-api and https://open-meteo.com/en/docs
Azimuth: 0 = south, -90 = east, 90 = west. Times are requested in Asia/Kolkata.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.integrations.weather.base import (
    CURRENT_VARS,
    FORECAST_VARS,
    HISTORY_VARS,
    CurrentConditions,
    HourlySeries,
    SourceInfo,
    WeatherRequestRejected,
    WeatherUnavailable,
)

log = logging.getLogger(__name__)

TIMEZONE = "Asia/Kolkata"
HISTORY_TIMEOUT_S = 30.0  # ten years of hourly data is a few MB
FORECAST_TIMEOUT_S = 10.0
HISTORY_SOURCE = "Open-Meteo Historical Weather API (ERA5 reanalysis)"
FORECAST_SOURCE = "Open-Meteo Forecast API"


class _ServerError(Exception):
    pass


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, (_ServerError, httpx.TimeoutException, httpx.TransportError))


class OpenMeteoProvider:
    is_mock = False

    def __init__(
        self,
        client: httpx.AsyncClient,
        archive_url: str,
        forecast_url: str,
        *,
        attempts: int = 3,
        backoff_s: float = 0.5,
    ) -> None:
        self._client = client
        self._archive_url = archive_url
        self._forecast_url = forecast_url
        self._attempts = attempts  # 1 try + 2 retries on 5xx and timeouts
        self._backoff_s = backoff_s

    async def _get(self, url: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._attempts),
            wait=wait_exponential(multiplier=self._backoff_s, max=4),
            retry=retry_if_exception(_retryable),
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    resp = await self._client.get(url, params=params, timeout=timeout)
                    if resp.status_code >= 500:
                        raise _ServerError(f"HTTP {resp.status_code}")
        except (_ServerError, httpx.HTTPError) as exc:
            log.warning("Open-Meteo request failed: %s", exc)
            raise WeatherUnavailable("The weather service is not responding. Try again shortly.") from exc

        if resp.status_code >= 400:
            reason = _reason(resp)
            raise WeatherRequestRejected(f"The weather service rejected the request: {reason}")
        try:
            return resp.json()
        except ValueError as exc:
            raise WeatherUnavailable("The weather service sent an unreadable response.") from exc

    @staticmethod
    def _hourly(body: dict[str, Any], names: tuple[str, ...], source: SourceInfo) -> HourlySeries:
        hourly = body.get("hourly") or {}
        times = hourly.get("time") or []
        values = {n: list(hourly.get(n) or [None] * len(times)) for n in names}
        return HourlySeries(times=times, values=values, units=body.get("hourly_units") or {}, source=source)

    async def hourly_history(
        self, lat: float, lon: float, tilt: float, azimuth: float, start: date, end: date
    ) -> HourlySeries:
        params = {
            "latitude": lat, "longitude": lon,
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "hourly": ",".join(HISTORY_VARS), "tilt": tilt, "azimuth": azimuth,
            "timezone": TIMEZONE,
        }
        body = await self._get(self._archive_url, params, HISTORY_TIMEOUT_S)
        return self._hourly(body, HISTORY_VARS, _source(HISTORY_SOURCE, self._archive_url))

    async def current(self, lat: float, lon: float) -> CurrentConditions:
        params = {"latitude": lat, "longitude": lon, "current": ",".join(CURRENT_VARS), "timezone": TIMEZONE}
        body = await self._get(self._forecast_url, params, FORECAST_TIMEOUT_S)
        current = body.get("current") or {}
        return CurrentConditions(
            time=current.get("time", ""),
            values={n: current.get(n) for n in CURRENT_VARS},
            units=body.get("current_units") or {},
            source=_source(FORECAST_SOURCE, self._forecast_url),
        )

    async def forecast(
        self, lat: float, lon: float, tilt: float, azimuth: float, days: int = 7
    ) -> HourlySeries:
        params = {
            "latitude": lat, "longitude": lon, "hourly": ",".join(FORECAST_VARS),
            "tilt": tilt, "azimuth": azimuth, "forecast_days": days, "timezone": TIMEZONE,
        }
        body = await self._get(self._forecast_url, params, FORECAST_TIMEOUT_S)
        return self._hourly(body, FORECAST_VARS, _source(FORECAST_SOURCE, self._forecast_url))


def _source(name: str, url: str) -> SourceInfo:
    return SourceInfo(name=name, url=url, retrieved_at=datetime.now(timezone.utc))


def _reason(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("reason") or f"HTTP {resp.status_code}")
    except ValueError:
        return f"HTTP {resp.status_code}"
