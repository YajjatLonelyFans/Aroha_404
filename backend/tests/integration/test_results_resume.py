"""What the results page needs: a saved estimate read back, and the season months for the chart."""

from tests.integration.journey import PIN_LAT, PIN_LON, walk_to_assessment


def _estimate(api, user_id, assessment_id):
    r = api.client.post("/api/solar/estimate", json={"user_id": user_id, "assessment_id": assessment_id})
    assert r.status_code == 201, r.text
    return r.json()


def test_estimate_reads_back_exactly(api):
    user_id, _, assessment_id = walk_to_assessment(api.client)
    created = _estimate(api, user_id, assessment_id)
    again = api.client.get(f"/api/solar/estimates/{created['estimate_id']}")
    assert again.status_code == 200 and again.json() == created
    assert created["sources"], "the weather source travels with the saved estimate"


def test_latest_estimate_is_listed_on_the_user(api):
    user_id, _, assessment_id = walk_to_assessment(api.client)
    _estimate(api, user_id, assessment_id)
    newest = _estimate(api, user_id, assessment_id)["estimate_id"]
    assert api.client.get(f"/api/users/{user_id}").json()["latest"]["estimate_id"] == newest


def test_unknown_estimate_is_404(api):
    r = api.client.get("/api/solar/estimates/" + "c" * 24)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_climatology_lists_every_month_in_one_season(api):
    r = api.client.get(f"/api/weather/climatology?lat={PIN_LAT}&lon={PIN_LON}&tilt=20&azimuth=0")
    assert r.status_code == 200, r.text
    seasons = r.json()["seasons"]
    assert sorted(m for months in seasons.values() for m in months) == list(range(1, 13))
    assert seasons == api.client.app.state.assumptions.seasons
