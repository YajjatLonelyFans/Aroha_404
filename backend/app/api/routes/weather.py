from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_weather_service
from app.schemas.weather import ClimatologyResponse, CurrentResponse, ForecastResponse
from app.services.weather_service import WeatherService

router = APIRouter(prefix="/weather", tags=["weather"])

Lat = Annotated[float, Query(ge=-90, le=90, description="Latitude (WGS84)")]
Lon = Annotated[float, Query(ge=-180, le=180, description="Longitude (WGS84)")]
Tilt = Annotated[float, Query(ge=0, lt=90, description="Panel tilt in degrees from horizontal")]
Azimuth = Annotated[float, Query(ge=-180, le=180, description="0 = south, -90 = east, 90 = west")]
Service = Annotated[WeatherService, Depends(get_weather_service)]


@router.get("/climatology", response_model=ClimatologyResponse)
async def climatology(lat: Lat, lon: Lon, tilt: Tilt, azimuth: Azimuth, svc: Service) -> ClimatologyResponse:
    """10-year monthly climatology for the spot, with seasonal notes and energy per kWp."""
    return await svc.climatology(lat, lon, tilt, azimuth)


@router.get("/current", response_model=CurrentResponse)
async def current(lat: Lat, lon: Lon, svc: Service) -> CurrentResponse:
    return await svc.current(lat, lon)


@router.get("/forecast", response_model=ForecastResponse)
async def forecast(lat: Lat, lon: Lon, tilt: Tilt, azimuth: Azimuth, svc: Service) -> ForecastResponse:
    """7-day short-term outlook. Never used in yearly or savings estimates."""
    return await svc.forecast(lat, lon, tilt, azimuth)
