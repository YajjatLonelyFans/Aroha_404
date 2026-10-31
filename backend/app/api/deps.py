"""FastAPI dependencies that assemble services from app state."""

from typing import Annotated

from fastapi import Depends, Request

from app.agents.orchestrator.pipeline import Orchestrator
from app.core.assumptions import Assumptions
from app.core.errors import AppError
from app.db.store import DocumentStore, MongoStore
from app.db.weather_repo import MongoWeatherRepo, NoCacheWeatherRepo, WeatherRepo
from app.services.application_service import ApplicationService
from app.services.geo_service import GeoService
from app.services.policy_service import PolicyService
from app.services.roof_service import RoofService
from app.services.solar_service import SolarService
from app.services.user_service import UserService
from app.services.weather_service import WeatherService


def get_assumptions(request: Request) -> Assumptions:
    return request.app.state.assumptions


def get_store(request: Request) -> DocumentStore:
    mongo = request.app.state.mongo
    if mongo is None:
        raise AppError("database_unavailable", "The database is not configured.", status_code=503, retryable=True)
    return MongoStore(mongo[request.app.state.settings.mongodb_db])


def weather_repo(request: Request) -> WeatherRepo:
    mongo = request.app.state.mongo
    # Mock data never goes into the shared database, so it cannot be mistaken for a live record.
    if mongo is None or request.app.state.weather_provider.is_mock:
        return NoCacheWeatherRepo()
    return MongoWeatherRepo(mongo[request.app.state.settings.mongodb_db])


AssumptionsDep = Annotated[Assumptions, Depends(get_assumptions)]
StoreDep = Annotated[DocumentStore, Depends(get_store)]


def get_weather_service(
    request: Request, assumptions: AssumptionsDep, repo: Annotated[WeatherRepo, Depends(weather_repo)]
) -> WeatherService:
    return WeatherService(request.app.state.weather_provider, repo, assumptions)


def get_user_service(request: Request, store: StoreDep, assumptions: AssumptionsDep) -> UserService:
    return UserService(store, assumptions, request.app.state.settings.meko_enabled_default)


def get_geo_service(request: Request, assumptions: AssumptionsDep) -> GeoService:
    return GeoService(request.app.state.geocoder, assumptions)


def get_roof_service(store: StoreDep, assumptions: AssumptionsDep) -> RoofService:
    return RoofService(store, assumptions)


def get_orchestrator(
    request: Request, store: StoreDep, weather: Annotated[WeatherService, Depends(get_weather_service)]
) -> Orchestrator:
    state = request.app.state
    return Orchestrator(store, weather, state.llm, state.memory, PolicyService(store), ApplicationService(store))


def get_policy_service(store: StoreDep) -> PolicyService:
    return PolicyService(store)


def get_application_service(store: StoreDep) -> ApplicationService:
    return ApplicationService(store)


def get_solar_service(
    store: StoreDep,
    assumptions: AssumptionsDep,
    weather: Annotated[WeatherService, Depends(get_weather_service)],
    policy: Annotated[PolicyService, Depends(get_policy_service)],
) -> SolarService:
    return SolarService(store, weather, assumptions, policy)
