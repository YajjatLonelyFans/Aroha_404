import logging

from app.core.logging import RedactSecrets, setup_logging


def _record(msg, *args):
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)


def test_secret_query_params_are_masked():
    rec = _record("GET %s", "https://api.maptiler.com/maps/satellite/256/1/0/0.jpg?key=abc123&x=1")
    RedactSecrets().filter(rec)
    assert rec.getMessage() == "GET https://api.maptiler.com/maps/satellite/256/1/0/0.jpg?key=<redacted>&x=1"


def test_token_and_other_lines_are_handled():
    rec = _record("tile ...MapServer/tile/1/0/0?token=SECRET")
    RedactSecrets().filter(rec)
    assert "SECRET" not in rec.getMessage()
    plain = _record("GET /api/health -> 200 in %d ms", 3)
    RedactSecrets().filter(plain)
    assert plain.getMessage() == "GET /api/health -> 200 in 3 ms"


def test_http_client_request_logs_are_quiet():
    setup_logging("INFO")
    assert all(logging.getLogger(n).getEffectiveLevel() >= logging.WARNING for n in ("httpx", "httpx2", "httpcore"))
