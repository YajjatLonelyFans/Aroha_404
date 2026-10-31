import json

import pytest

from tests.integration.journey import assess, create_property, create_user
from tests.unit.helpers import geojson_rect


@pytest.fixture
def ids(api):
    user_id = create_user(api.client)
    return user_id, create_property(api.client, user_id)


def test_traced_flat_roof(api, ids):
    r = assess(api.client, *ids)
    assert r.status_code == 201, r.text
    body = r.json()
    # 10 x 5 m with a 0.5 m setback → 9 x 4 m usable.
    assert body["outline_area_m2"] == pytest.approx(50, abs=0.5)
    assert body["usable_area_m2"] == pytest.approx(36, abs=0.1)
    assert body["setback_area_m2"] == pytest.approx(14, abs=0.5)
    assert body["panel_count"] > 0
    assert body["capacity_kwp"]["likely"] == body["panel_count"] * 0.5
    assert body["panel_layout"]["type"] == "FeatureCollection"
    assert len(body["panel_layout"]["features"]) == body["panel_count"]
    assert body["array_tilt_deg"] == 20 and body["array_azimuth_deg"] == 0
    assert body["confidence"] == "high" and body["traced"] is True
    assert any("facing south" in s for s in body["assumptions"])


def test_assessment_is_saved_and_property_updated(api, ids):
    user_id, property_id = ids
    body = assess(api.client, user_id, property_id, shading={"south": "partial"}).json()
    saved = api.store.data["roof_assessments"][body["assessment_id"]]
    assert saved["inputs_hash"] and saved["model_version"] == "roof-1.0.0"
    prop = api.store.data["properties"][property_id]
    assert prop["outline"]["type"] == "Polygon"
    assert prop["shading"]["south"] == "partial"


def test_same_inputs_give_the_same_layout(api, ids):
    a = assess(api.client, *ids).json()
    b = assess(api.client, *ids).json()
    assert json.dumps(a["panel_layout"]) == json.dumps(b["panel_layout"])
    saved = api.store.data["roof_assessments"]
    assert saved[a["assessment_id"]]["inputs_hash"] == saved[b["assessment_id"]]["inputs_hash"]


def test_no_go_area_reduces_usable_area(api, ids):
    tank = {"kind": "water_tank", "geometry": geojson_rect(2, 2, x=4, y=1.5)}
    body = assess(api.client, *ids, no_go_areas=[tank]).json()
    assert body["no_go_area_m2"] == pytest.approx(4, abs=0.1)
    assert body["usable_area_m2"] == pytest.approx(32, abs=0.1)


def test_heavy_shade_lowers_min_and_confidence(api, ids):
    body = assess(api.client, *ids, shading={"west": "heavy"}).json()
    assert body["capacity_kwp"]["min"] < body["capacity_kwp"]["likely"]
    assert body["confidence"] == "low"
    assert body["shading_loss_fraction"] == 0.15
    assert "heavy_shade_west" in [c["code"] for c in body["constraints"]]


def test_manual_dimensions_fallback(api, ids):
    user_id, property_id = ids
    r = assess(api.client, user_id, property_id, outline=None,
               manual_dimensions={"length_m": 10, "width_m": 5, "no_go_areas_m2": [4]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["usable_area_m2"] == 32
    assert body["panel_layout"] is None and body["traced"] is False
    assert body["confidence"] == "medium"
    assert any("approximate" in s for s in body["assumptions"])


def test_sloped_roof_uses_its_own_angle(api, ids):
    body = assess(api.client, *ids, roof_type="sloped", slope_tilt_deg=25, slope_azimuth_deg=-90).json()
    assert body["array_tilt_deg"] == 25 and body["array_azimuth_deg"] == -90
    assert any("facing east" in s for s in body["assumptions"])


@pytest.mark.parametrize("change", [
    {"roof_type": "sloped"},  # missing slope values
    {"manual_dimensions": {"length_m": 10, "width_m": 5}},  # both outline and manual
    {"outline": None},  # neither
    {"shading": {"south": "total"}},
])
def test_invalid_requests_are_422(api, ids, change):
    r = assess(api.client, *ids, **change)
    assert r.status_code == 422, r.text


def test_outline_outside_delhi_is_422(api, ids):
    mumbai = {"type": "Polygon", "coordinates": [[[72.8, 19.0], [72.8001, 19.0], [72.8001, 19.0001], [72.8, 19.0001], [72.8, 19.0]]]}
    r = assess(api.client, *ids, outline=mumbai)
    assert r.status_code == 422 and r.json()["error"]["code"] == "outside_delhi"


def test_someone_elses_property_is_404(api, ids):
    _, property_id = ids
    other = create_user(api.client)
    assert assess(api.client, other, property_id).status_code == 404


def test_missing_assumption_names_the_field(api, ids):
    api.set_assumptions(layout={"edge_setback_m": 0.5, "no_go_clearance_m": 0.0, "row_gap_m": None,
                                "flush_gap_m": 0.05, "default_flat_tilt_deg": 20, "default_azimuth_deg": 0})
    r = assess(api.client, *ids)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "assumption_missing"
    assert r.json()["error"]["details"]["field"] == "layout.row_gap_m"
