"""Warm the weather cache for the demo locations so judging does not depend on venue Wi-Fi.

Usage (from backend/, venv active):  python -m scripts.warm_cache
Fetches and stores the 10-year climatology, current conditions and 7-day outlook
for each spot at the default flat-roof tilt and azimuth. Safe to run again.
"""

import asyncio
import sys
import time

import httpx

from app.core.assumptions import load_assumptions
from app.core.settings import get_settings
from app.db.client import create_client
from app.db.weather_repo import MongoWeatherRepo
from app.integrations.weather.open_meteo import OpenMeteoProvider
from app.services.weather_service import WeatherService

# Public places only (the demo traces a public building, never a private home).
DEMO_SPOTS = {
    "SSCBS campus, Rohini": (28.7327, 77.1190),
    "Connaught Place": (28.6318, 77.2194),
}


async def main() -> int:
    s = get_settings()
    a = load_assumptions()
    mongo = create_client(s)
    if mongo is None:
        print("MONGODB_URI is not set; nothing to warm.")
        return 1
    tilt, azimuth = a.require("layout.default_flat_tilt_deg"), a.require("layout.default_azimuth_deg")
    failures = 0
    async with httpx.AsyncClient() as http:
        provider = OpenMeteoProvider(http, s.open_meteo_archive_url, s.open_meteo_forecast_url)
        svc = WeatherService(provider, MongoWeatherRepo(mongo[s.mongodb_db]), a)
        for name, (lat, lon) in DEMO_SPOTS.items():
            for label, call in (("climatology", svc.climatology(lat, lon, tilt, azimuth)),
                                ("forecast", svc.forecast(lat, lon, tilt, azimuth)),
                                ("current", svc.current(lat, lon))):
                start = time.perf_counter()
                try:
                    result = await call
                    print(f"  {name:22} {label:12} ok in {time.perf_counter() - start:4.1f}s "
                          f"({'already cached' if result.cached else 'fetched and cached'})")
                except Exception as exc:  # report every spot, then exit non-zero
                    failures += 1
                    print(f"  {name:22} {label:12} FAILED: {exc}")
    await mongo.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
