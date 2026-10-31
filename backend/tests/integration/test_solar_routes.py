import pytest

from app.services.solar_service import option_counts
from tests.integration.journey import create_property, create_user, assess, walk_to_assessment
from tests.weather_data import JOURNEY_READY


def _estimate(api, user_id, assessment_id, **extra):
    return api.client.post("/api/solar/estimate", json={"user_id": user_id, "assessment_id": assessment_id, **extra})


def test_default_estimate(api):
    user_id, _, assessment_id = walk_to_assessment(api.client)
    r = _estimate(api, user_id, assessment_id)
    assert r.status_code == 201, r.text
    body = r.json()

    assert 1 <= len(body["options"]) <= 3
    recommended = [o for o in body["options"] if o["recommended"]]
    assert len(recommended) == 1 and recommended[0]["capacity_kwp"] == body["recommended_kwp"]
    assert body["binding_constraint"] in ("roof", "consumption")
    assert body["recommended_kwp"] <= body["roof_kwp"]

    for o in body["options"]:
        assert len(o["monthly_kwh"]) == 12
        for m in o["monthly_kwh"]:
            assert m["p10"] <= m["median"] <= m["p90"]
        assert o["gross_cost_inr"] == o["capacity_kwp"] * 60000
        assert o["net_cost_inr"] == o["gross_cost_inr"]  # no subsidy yet
        s, p = o["annual_savings_inr"], o["payback_years"]
        assert s["low"] <= s["likely"] <= s["high"]
        assert p["low"] <= p["likely"] <= p["high"]
        assert o["missing"] == []

    assert "not guarantees" in body["disclaimer"]
    assert any("Subsidies are not applied" in n for n in body["notes"])
    assert "Open-Meteo" in body["sources"][0]["note"]
    assert body["estimate_id"] in api.store.data["solar_estimates"]


def test_generation_matches_the_hourly_model(api):
    user_id, _, assessment_id = walk_to_assessment(api.client)
    body = _estimate(api, user_id, assessment_id).json()
    # Synthetic weather: 12 h/day at 500 W/m², 25 °C air → per kWp per hour:
    t_cell = 25 + (45 - 20) / 800 * 500
    per_kwp_hour = 0.5 * (1 - 0.004 * (t_cell - 25)) * (1 - 0.14)
    o = body["options"][0]
    assert o["monthly_kwh"][0]["median"] == pytest.approx(o["capacity_kwp"] * per_kwp_hour * 12 * 31, abs=1)


def test_more_use_than_the_roof_can_supply_binds_on_roof(api):
    user_id, _, assessment_id = walk_to_assessment(api.client)
    body = _estimate(api, user_id, assessment_id, monthly_units_kwh=5000).json()
    assert body["binding_constraint"] == "roof"
    assert body["recommended_kwp"] == body["roof_kwp"]
    assert body["monthly_units_kwh"] == 5000


def test_requested_capacities(api):
    user_id, _, assessment_id = walk_to_assessment(api.client)
    body = _estimate(api, user_id, assessment_id, capacities_kwp=[2, 3]).json()
    assert [o["capacity_kwp"] for o in body["options"]] == [2.0, 3.0]


def test_capacity_beyond_the_roof_is_422(api):
    user_id, _, assessment_id = walk_to_assessment(api.client)
    r = _estimate(api, user_id, assessment_id, capacities_kwp=[100])
    assert r.status_code == 422 and r.json()["error"]["code"] == "capacity_exceeds_roof"


def test_shade_lowers_generation(api):
    user_id = create_user(api.client)
    property_id = create_property(api.client, user_id)
    clear = assess(api.client, user_id, property_id).json()
    shaded = assess(api.client, user_id, property_id, shading={"south": "partial"}).json()
    a = _estimate(api, user_id, clear["assessment_id"], capacities_kwp=[3]).json()["options"][0]
    b = _estimate(api, user_id, shaded["assessment_id"], capacities_kwp=[3]).json()["options"][0]
    assert b["annual_kwh"]["median"] == pytest.approx(a["annual_kwh"]["median"] * 0.95, abs=1)


def test_other_discom_has_no_savings_but_says_why(api):
    user_id = create_user(api.client, discom="TPDDL")
    property_id = create_property(api.client, user_id)
    assessment_id = assess(api.client, user_id, property_id).json()["assessment_id"]
    body = _estimate(api, user_id, assessment_id).json()
    assert all(o["annual_savings_inr"]["likely"] is None for o in body["options"])
    assert all(o["gross_cost_inr"] is not None for o in body["options"])
    assert any("TPDDL" in n for n in body["notes"])


def test_missing_cost_leaves_cost_empty_with_reason(api):
    api.set_assumptions(costs={"cost_per_kwp_inr": None})
    user_id, _, assessment_id = walk_to_assessment(api.client)
    o = _estimate(api, user_id, assessment_id).json()["options"][0]
    assert o["gross_cost_inr"] is None and o["payback_years"]["likely"] is None
    assert o["annual_savings_inr"]["likely"] is not None
    assert o["missing"]


def test_yield_needs_module_assumptions(api):
    user_id, _, assessment_id = walk_to_assessment(api.client)
    api.set_assumptions(module={**JOURNEY_READY["module"], "gamma_per_c": None})
    r = _estimate(api, user_id, assessment_id)
    assert r.status_code == 503 and r.json()["error"]["code"] == "yield_unavailable"


def test_someone_elses_assessment_is_404(api):
    _, _, assessment_id = walk_to_assessment(api.client)
    other = create_user(api.client)
    assert _estimate(api, other, assessment_id).status_code == 404


def test_weather_outage_is_503(api):
    user_id, _, assessment_id = walk_to_assessment(api.client)
    api.weather.fail = True
    r = _estimate(api, user_id, assessment_id)
    assert r.status_code == 503 and r.json()["error"]["code"] == "weather_unavailable"


@pytest.mark.parametrize("recommended, roof_max, expected", [
    (6, 20, [4, 6, 8]),  # 500 Wp → 2 panels per kW either side
    (1, 20, [1, 3]),
    (19, 20, [17, 19]),
    (1, 1, [1]),
])
def test_default_option_counts(recommended, roof_max, expected):
    assert option_counts(recommended, roof_max, 500, None) == expected
