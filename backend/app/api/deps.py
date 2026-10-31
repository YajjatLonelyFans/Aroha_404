"""FastAPI dependencies that assemble services from app state."""

from fastapi import Request

from app.db.weather_repo import MongoWeatherRepo, NoCacheWeatherRepo, WeatherRepo
from app.services.weather_service import WeatherService


def weather_repo(request: Request) -> WeatherRepo:
    mongo = request.app.state.mongo
    # Mock data never goes into the shared database, so it cannot be mistaken for a live record.
    if mongo is None or request.app.state.weather_provider.is_mock:
        return NoCacheWeatherRepo()
    return MongoWeatherRepo(mongo[request.app.state.settings.mongodb_db])


def get_weather_service(request: Request) -> WeatherService:
    state = request.app.state
    return WeatherService(state.weather_provider, weather_repo(request), state.assumptions)
