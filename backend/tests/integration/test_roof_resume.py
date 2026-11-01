"""Reading back what was drawn and the last result, so a returning homeowner sees them again."""

import pytest

from tests.integration.journey import ROOF, assess, create_property, create_user
from tests.unit.helpers import geojson_rect


@pytest.fixture
def ids(api):
    user_id = create_user(api.client)
    return user_id, create_property(api.client, user_id)


def test_property_has_no_roof_before_an_assessment(api, ids):
    assert api.client.get(f"/api/properties/{ids[1]}").json()["roof"] is None


def test_property_returns_the_drawing_and_answers(api, ids):
    tank = {"kind": "water_tank", "geometry": geojson_rect(1, 1, x=2, y=2)}
    shading = {"east": "partial", "south": "none", "west": "heavy", "north": "none"}
    assert assess(api.client, *ids, no_go_areas=[tank], shading=shading).status_code == 201
    roof = api.client.get(f"/api/properties/{ids[1]}").json()["roof"]
    assert roof["outline"] == ROOF and roof["no_go_areas"] == [tank]
    assert roof["roof_type"] == "flat" and roof["shading"] == shading and roof["manual_dimensions"] is None


def test_property_returns_manual_dimensions_and_slope(api, ids):
    manual = {"length_m": 10, "width_m": 5, "no_go_areas_m2": [4]}
    r = assess(api.client, *ids, outline=None, manual_dimensions=manual, roof_type="sloped",
               slope_tilt_deg=15, slope_azimuth_deg=-45)
    assert r.status_code == 201, r.text
    roof = api.client.get(f"/api/properties/{ids[1]}").json()["roof"]
    assert roof["outline"] is None and roof["manual_dimensions"] == manual
    assert (roof["roof_type"], roof["slope_tilt_deg"], roof["slope_azimuth_deg"]) == ("sloped", 15, -45)


def test_assessment_reads_back_exactly(api, ids):
    created = assess(api.client, *ids).json()
    again = api.client.get(f"/api/roof/assessments/{created['assessment_id']}")
    assert again.status_code == 200 and again.json() == created


def test_latest_assessment_is_listed_on_the_user(api, ids):
    assess(api.client, *ids)
    newest = assess(api.client, *ids).json()["assessment_id"]
    assert api.client.get(f"/api/users/{ids[0]}").json()["latest"]["assessment_id"] == newest


def test_unknown_assessment_is_404(api):
    r = api.client.get("/api/roof/assessments/" + "b" * 24)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
