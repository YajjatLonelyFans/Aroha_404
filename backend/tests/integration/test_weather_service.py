from datetime import date, datetime, timedelta, timezone

import pytest

from app.domain.errors import DomainError
from app.integrations.weather.base import WeatherUnavailable
from app.services.weather_service import WeatherService, grid_key, specific_yield_from_doc
from tests.fakes import FakeWeatherProvider as FakeProvider
from tests.fakes import FakeWeatherRepo as FakeRepo
from tests.weather_data import OUTLOOK_READY, UNSET, YIELD_READY, assumptions

NOW = datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)
LAT, LON = 28.6139, 77.2090


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


def make(provider=None, repo=None, clock=None, **sections):
    a = assumptions(**{**UNSET, **sections})
    return WeatherService(provider or FakeProvider(), repo or FakeRepo(), a, clock or Clock())


def test_grid_key():
    assert grid_key(28.6139, 77.2090) == (28.61, 77.21, "28.61_77.21")


async def test_climatology_fetches_rounded_10_years_and_caches():
    provider, repo = FakeProvider(), FakeRepo()
    svc = make(provider, repo, **YIELD_READY)
    first = await svc.climatology(LAT, LON, 19.6, -0.4)
    assert provider.history_args == (28.61, 77.21, 20.0, -0.0, date(2016, 1, 1), date(2025, 12, 31))
    assert first.cached is False and first.period == "2016-2025"
    assert len(first.years) == 10 and len(first.monthly) == 12
    assert first.climatology_id == "clim-1"

    second = await svc.climatology(LAT, LON, 20, 0)
    assert second.cached is True
    assert provider.calls["history"] == 1
    assert second.climatology_id == first.climatology_id


async def test_specific_yield_matches_the_hourly_model():
    svc = make(**YIELD_READY)
    r = await svc.climatology(LAT, LON, 20, 0)
    # Synthetic data: 12 h/day at 500 W/m², 25 °C air → cell 40.625 °C.
    t_cell = 25 + (45 - 20) / 800 * 500
    per_hour = 0.5 * (1 - 0.004 * (t_cell - 25)) * (1 - 0.14)
    assert r.specific_yield.monthly_kwh_per_kwp[0].median == pytest.approx(31 * 12 * per_hour, abs=0.05)
    assert r.specific_yield.years_used == 10
    assert r.monthly[0].gti_kwh_m2.median == pytest.approx(186.0)


async def test_yield_is_absent_until_assumptions_are_set():
    r = await make().climatology(LAT, LON, 20, 0)
    assert r.specific_yield is None
    assert any("gamma_per_c" in n for n in r.notes)
    assert r.monthly[0].gti_kwh_m2.median is not None


async def test_changed_assumptions_trigger_a_refetch():
    provider, repo = FakeProvider(), FakeRepo()
    await make(provider, repo).climatology(LAT, LON, 20, 0)
    r = await make(provider, repo, **YIELD_READY).climatology(LAT, LON, 20, 0)
    assert provider.calls["history"] == 2
    assert r.cached is False and r.specific_yield is not None


async def test_mock_cache_is_never_served_as_live():
    repo = FakeRepo()
    await make(FakeProvider(is_mock=True), repo).climatology(LAT, LON, 20, 0)
    live = FakeProvider(is_mock=False)
    r = await make(live, repo).climatology(LAT, LON, 20, 0)
    assert live.calls["history"] == 1 and r.is_mock is False


async def test_failed_refresh_serves_cached_copy_with_note():
    repo = FakeRepo()
    await make(FakeProvider(), repo).climatology(LAT, LON, 20, 0)
    r = await make(FakeProvider(fail=True), repo, **YIELD_READY).climatology(LAT, LON, 20, 0)
    assert r.cached is True
    assert any("saved earlier" in n for n in r.notes)


async def test_failure_without_cache_raises():
    with pytest.raises(WeatherUnavailable):
        await make(FakeProvider(fail=True)).climatology(LAT, LON, 20, 0)


async def test_outside_delhi_is_rejected():
    with pytest.raises(DomainError) as exc:
        await make().climatology(19.07, 72.88, 20, 0)
    assert exc.value.code == "outside_delhi"


async def test_season_notes_and_provenance():
    r = await make(**YIELD_READY).climatology(LAT, LON, 20, 0)
    assert r.season_notes and all(n.evidence_fields for n in r.season_notes)
    assert r.sources[0].retrieved_at.tzinfo is not None
    assert "Open-Meteo" in r.sources[0].note
    assert r.missing.hours == 0


async def test_stored_yield_round_trips():
    repo = FakeRepo()
    await make(repo=repo, **YIELD_READY).climatology(LAT, LON, 20, 0)
    doc = next(iter(repo.climatology.values()))
    sy = specific_yield_from_doc(doc)
    assert sy.kwh_per_kwp.shape == (10, 12)
    assert sy.excluded == ()


async def test_current_is_cached_for_an_hour():
    provider, repo, clock = FakeProvider(), FakeRepo(), Clock()
    svc = make(provider, repo, clock)
    first = await svc.current(LAT, LON)
    assert first.observation.temperature_c == 24.5 and first.observation.is_day is True
    assert (await svc.current(LAT, LON)).cached is True
    clock.now = NOW + timedelta(minutes=61)
    assert (await svc.current(LAT, LON)).cached is False
    assert provider.calls["current"] == 2


async def test_forecast_unlabelled_without_rule_or_climatology():
    r = await make().forecast(LAT, LON, 20, 0)
    assert r.label == "Short-term outlook"
    assert len(r.daily) == 7
    assert all(d.outlook is None for d in r.daily)
    assert any("Never used" in n for n in r.notes)


async def test_forecast_labels_days_against_climatology():
    provider, repo = FakeProvider(), FakeRepo()
    svc = make(provider, repo, **YIELD_READY, **OUTLOOK_READY)
    await svc.climatology(LAT, LON, 20, 0)
    r = await svc.forecast(LAT, LON, 20, 0)
    # Forecast days equal the typical day exactly (same synthetic pattern) → ratio 1 → sunny.
    assert all(d.outlook == "sunny" for d in r.daily)
    assert (await svc.forecast(LAT, LON, 20, 0)).cached is True
    assert provider.calls["forecast"] == 1
