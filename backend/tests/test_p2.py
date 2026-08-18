"""P2 tests: metrics exposition, circuit breakers, graceful degradation."""
import pytest


def test_metrics_endpoint_prometheus_format(client, admin_client):
    # generate some traffic first
    client.get("/api/reports?page_size=1")
    r = client.get("/api/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    assert "civiclens_http_requests_total" in body
    assert "civiclens_http_request_seconds_bucket" in body
    assert "civiclens_open_reports" in body
    # cardinality control: report ids collapsed to :id
    assert ":id" in body or "reports/" not in body


def test_metrics_path_normalization():
    from app.metrics import _normalize_path
    assert _normalize_path("/api/reports/9f43224c19c9aaaa1111222233334444/media") == "/api/reports/:id/media"
    assert _normalize_path("/api/reports/CL-9F43AB") == "/api/reports/:code"
    assert _normalize_path("/api/reports") == "/api/reports"


def test_circuit_breaker_opens_and_recovers():
    from app.circuit import CircuitBreaker, CircuitOpen

    calls = {"n": 0}
    def failing():
        calls["n"] += 1
        raise ConnectionError("down")

    cb = CircuitBreaker("test", failure_threshold=3, reset_timeout=0.2)
    for _ in range(3):
        with pytest.raises(ConnectionError):
            cb.call(failing)
    assert cb.state == "open"
    # short-circuits: underlying function NOT called
    before = calls["n"]
    with pytest.raises(CircuitOpen):
        cb.call(failing)
    assert calls["n"] == before

    # after reset timeout -> half-open -> success closes it
    import time
    time.sleep(0.25)
    assert cb.state == "half-open"
    assert cb.call(lambda: "ok") == "ok"
    assert cb.state == "closed"


def test_circuit_half_open_failure_reopens():
    from app.circuit import CircuitBreaker
    import time
    cb = CircuitBreaker("test2", failure_threshold=1, reset_timeout=0.1)
    with pytest.raises(ValueError):
        cb.call(lambda: (_ for _ in ()).throw(ValueError()))
    assert cb.state == "open"
    time.sleep(0.15)
    with pytest.raises(ValueError):  # half-open probe fails
        cb.call(lambda: (_ for _ in ()).throw(ValueError()))
    assert cb.state == "open"        # straight back to open


def test_smtp_circuit_never_breaks_notify(client, monkeypatch):
    """SMTP circuit open -> notify still records in-app + SSE, no exception."""
    from app import notify as notify_mod
    from app.circuit import smtp_breaker
    from app.db import SessionLocal
    from app.models import Notification, User

    class Boom:
        def send(self, *a): raise ConnectionError("smtp down")
    monkeypatch.setattr(notify_mod, "_email_channel", lambda: Boom())

    db = SessionLocal()
    user = db.query(User).filter_by(email="cit@test.et").first()
    before = db.query(Notification).filter_by(user_id=user.id).count()
    for _ in range(5):    # trip the breaker
        notify_mod.notify(db, user, "test", "Breaker test", "x")
    after = db.query(Notification).filter_by(user_id=user.id).count()
    assert after == before + 5           # all in-app notifications delivered
    assert smtp_breaker.state == "open"  # email path safely short-circuited
    smtp_breaker._record_success()       # reset for other tests
    db.close()


def test_readiness_exposes_circuit_states(client):
    r = client.get("/api/ready")
    checks = r.json()["checks"]
    assert "circuits" in checks
    assert set(checks["circuits"]) == {"ai_service", "smtp", "storage"}
