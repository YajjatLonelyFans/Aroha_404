from types import SimpleNamespace

from app.api.deps import weather_repo
from app.db.weather_repo import MongoWeatherRepo, NoCacheWeatherRepo
from app.integrations.weather.mock import MockWeatherProvider


class _Mongo:
    """Stands in for AsyncMongoClient: client[db][collection] returns a placeholder."""

    def __getitem__(self, name):
        return {"weather_records": None, "weather_forecasts": None}


def _request(provider, mongo):
    state = SimpleNamespace(mongo=mongo, weather_provider=provider,
                            settings=SimpleNamespace(mongodb_db="aroha_db"))
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_mock_weather_never_writes_to_the_database():
    assert isinstance(weather_repo(_request(MockWeatherProvider(), _Mongo())), NoCacheWeatherRepo)


def test_live_weather_uses_the_database():
    live = SimpleNamespace(is_mock=False)
    assert isinstance(weather_repo(_request(live, _Mongo())), MongoWeatherRepo)


def test_no_database_means_no_cache():
    live = SimpleNamespace(is_mock=False)
    assert isinstance(weather_repo(_request(live, None)), NoCacheWeatherRepo)
