from tests.integration.journey import PIN_LAT, PIN_LON, USER, create_property, create_user, walk_to_assessment


def test_eligible_user(api):
    r = api.client.post("/api/users", json=USER)
    assert r.status_code == 201
    body = r.json()
    assert body["eligible_to_continue"] is True and body["reason"] is None
    stored = next(iter(api.store.data["users"].values()))
    assert stored["monthly_units_kwh"] == 350 and stored["created_at"].tzinfo is not None


def test_no_roof_rights_stops_with_a_reason(api):
    body = api.client.post("/api/users", json={**USER, "property_type": "builder_floor", "has_roof_rights": False}).json()
    assert body["eligible_to_continue"] is False
    assert "right to use the roof" in body["reason"]


def test_out_of_scope_property(api):
    body = api.client.post("/api/users", json={**USER, "property_type": "other"}).json()
    assert body["eligible_to_continue"] is False


def test_bad_answers_are_422(api):
    for bad in ({"discom": "XYZ"}, {"monthly_units_kwh": 0}, {"has_roof_rights": None}):
        r = api.client.post("/api/users", json={**USER, **bad})
        assert r.status_code == 422, bad


def test_summary_tracks_latest_ids(api):
    user_id = create_user(api.client)
    empty = api.client.get(f"/api/users/{user_id}").json()
    assert empty["latest"] == {"property_id": None, "assessment_id": None, "estimate_id": None, "application_id": None}

    walker, property_id, assessment_id = walk_to_assessment(api.client)
    latest = api.client.get(f"/api/users/{walker}").json()["latest"]
    assert latest["property_id"] == property_id and latest["assessment_id"] == assessment_id


def test_unknown_or_malformed_user_is_404(api):
    for user_id in ("0" * 24, "not-an-id"):
        r = api.client.get(f"/api/users/{user_id}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_property_saves_the_pin(api):
    user_id = create_user(api.client)
    r = api.client.post("/api/properties", json={"user_id": user_id, "lat": PIN_LAT, "lon": PIN_LON,
                                                  "address_text": "Test address"})
    assert r.status_code == 201
    prop = api.store.data["properties"][r.json()["property_id"]]
    assert prop["pin"] == {"type": "Point", "coordinates": [PIN_LON, PIN_LAT]}
    assert prop["grid_key"] == r.json()["grid_key"]


def test_property_outside_delhi_is_422(api):
    user_id = create_user(api.client)
    r = api.client.post("/api/properties", json={"user_id": user_id, "lat": 19.07, "lon": 72.88})
    assert r.status_code == 422 and r.json()["error"]["code"] == "outside_delhi"


def test_ineligible_user_cannot_add_a_property(api):
    user_id = create_user(api.client, has_roof_rights=False)
    r = api.client.post("/api/properties", json={"user_id": user_id, "lat": PIN_LAT, "lon": PIN_LON})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_eligible"


def test_property_for_unknown_user_is_404(api):
    r = api.client.post("/api/properties", json={"user_id": "f" * 24, "lat": PIN_LAT, "lon": PIN_LON})
    assert r.status_code == 404


def test_geo_search_keeps_delhi_results_only(api):
    body = api.client.get("/api/geo/search?q=Connaught Place").json()
    assert [p["display_name"][:15] for p in body["results"]] == ["Connaught Place"]
    assert body["attribution"] == "© OpenStreetMap contributors"
    assert body["is_mock"] is False


def test_geo_search_needs_three_characters(api):
    assert api.client.get("/api/geo/search?q=cp").status_code == 422
    assert api.geocoder.queries == []


def test_geo_search_outage_is_503(api):
    api.geocoder.fail = True
    r = api.client.get("/api/geo/search?q=Connaught Place")
    assert r.status_code == 503 and r.json()["error"]["retryable"] is True


def test_create_property_helper_round_trip(api):
    user_id = create_user(api.client)
    assert create_property(api.client, user_id)
