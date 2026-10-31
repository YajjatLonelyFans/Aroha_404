import httpx
import respx
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _client(**overrides) -> TestClient:
    settings = Settings(_env_file=None, **overrides)
    return TestClient(create_app(settings))


def test_health_without_mongo_is_degraded_but_alive():
    with _client() as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["mongo"]["status"] == "not_configured"
    assert body["dependencies"]["open_meteo"]["status"] == "configured"
    assert body["assumptions"]["complete"] is False
    assert "module.wp" in body["assumptions"]["missing"]


def test_placeholder_keys_count_as_not_configured():
    with _client(meko_api_key="<from-meko-portal>", llm_api_key="<key>") as client:
        deps = client.get("/api/health").json()["dependencies"]
    assert deps["meko"]["status"] == "not_configured"
    assert deps["llm"]["status"] == "not_configured"


def test_unreachable_mongo_reports_error():
    # Port 1 refuses connections; the short timeout keeps the test fast.
    with _client(mongodb_uri="mongodb://127.0.0.1:1/", mongodb_timeout_ms=300) as client:
        mongo = client.get("/api/health").json()["dependencies"]["mongo"]
    assert mongo["status"] == "error"
    assert mongo["detail"]


def test_mocks_are_labelled():
    with _client(use_mock_weather=True, use_mock_meko=True, use_mock_llm=True) as client:
        deps = client.get("/api/health").json()["dependencies"]
    for name in ("open_meteo", "meko", "llm"):
        assert deps[name]["is_mock"] is True


@respx.mock
def test_deep_check_reaches_open_meteo():
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json={"current": {}}))
    with _client() as client:
        om = client.get("/api/health?deep=true").json()["dependencies"]["open_meteo"]
    assert om["status"] == "ok"


@respx.mock
def test_deep_check_reports_open_meteo_failure():
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(503))
    with _client() as client:
        om = client.get("/api/health?deep=true").json()["dependencies"]["open_meteo"]
    assert om["status"] == "error"


def test_unknown_route_uses_error_envelope():
    with _client() as client:
        resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "http_404"


def test_bad_query_uses_error_envelope():
    with _client() as client:
        resp = client.get("/api/health?deep=maybe")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"
