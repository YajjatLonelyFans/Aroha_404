"""Helpers that walk the journey through the API."""

from app.domain.geometry import to_wgs84
from tests.unit.helpers import geojson_rect, metric_rect

# A 10 x 5 m roof in South Delhi, and its centre as the pin.
ROOF = geojson_rect(10, 5)
PIN_LON, PIN_LAT = to_wgs84(metric_rect(10, 5)).centroid.coords[0]

USER = {
    "display_name": "Demo Homeowner",
    "property_type": "independent_house",
    "has_roof_rights": True,
    "monthly_units_kwh": 350,
    "discom": "BRPL",
}


def create_user(client, **overrides) -> str:
    r = client.post("/api/users", json={**USER, **overrides})
    assert r.status_code == 201, r.text
    return r.json()["user_id"]


def create_property(client, user_id) -> str:
    r = client.post("/api/properties", json={"user_id": user_id, "lat": PIN_LAT, "lon": PIN_LON})
    assert r.status_code == 201, r.text
    return r.json()["property_id"]


def assess(client, user_id, property_id, **overrides):
    body = {"user_id": user_id, "property_id": property_id, "outline": ROOF, "roof_type": "flat"}
    body.update(overrides)
    return client.post("/api/roof/assess", json=body)


def walk_to_assessment(client) -> tuple[str, str, str]:
    user_id = create_user(client)
    property_id = create_property(client, user_id)
    r = assess(client, user_id, property_id)
    assert r.status_code == 201, r.text
    return user_id, property_id, r.json()["assessment_id"]
