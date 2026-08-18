"""Pluggable duplicate-analyzer tests."""
from app.db import SessionLocal
from app.duplicates import GeoTextAnalyzer, find_duplicates, get_analyzers
from app.models import Report, ReportStatus


def _mk(db, title, desc, lat, lng, cat="Water"):
    r = Report(title=title, description=desc, latitude=lat, longitude=lng,
               user_category=cat, category=cat, status=ReportStatus.submitted,
               city="Addis Ababa")
    db.add(r)
    db.commit()
    return r


def test_geo_text_finds_nearby_similar(client):
    db = SessionLocal()
    try:
        a = _mk(db, "Big water pipe leak near market",
                "Large water pipe leaking near the central market entrance flooding street", 9.100, 38.700)
        b = _mk(db, "Water pipe leaking at market entrance",
                "The water pipe near the central market entrance is leaking and flooding", 9.1003, 38.7003)
        cands = find_duplicates(db, b)
        assert any(c.report.id == a.id for c in cands)
        top = next(c for c in cands if c.report.id == a.id)
        assert top.analyzer == "geo_text"
        assert 0 < top.score <= 1
        assert "text overlap" in top.reason
    finally:
        db.close()


def test_geo_text_ignores_far_away(client):
    db = SessionLocal()
    try:
        far = _mk(db, "Water pipe leak in Hawassa",
                  "Large water pipe leaking near the lake shore in Hawassa town", 7.05, 38.47)
        b = _mk(db, "Water pipe leak follow-up",
                "Large water pipe leaking near the central market entrance again", 9.100, 38.700)
        cands = find_duplicates(db, b)
        assert all(c.report.id != far.id for c in cands)
    finally:
        db.close()


def test_analyzer_registry_configurable(monkeypatch):
    from app import duplicates as dup
    monkeypatch.setattr(dup.settings, "duplicate_analyzers", "geo_text")
    assert [a.name for a in get_analyzers()] == ["geo_text"]
    # unknown analyzers are ignored, not fatal (forward compatibility)
    monkeypatch.setattr(dup.settings, "duplicate_analyzers", "geo_text,image_embedding")
    assert [a.name for a in get_analyzers()] == ["geo_text"]


def test_duplicates_endpoint_staff_only(client, admin_client):
    r = admin_client.post("/api/reports", json={
        "title": "Dup endpoint test", "description": "Testing the duplicates endpoint here.",
        "category": "Water", "city": "Addis Ababa", "latitude": 9.2, "longitude": 38.8})
    rid = r.json()["id"]
    assert admin_client.get(f"/api/reports/{rid}/duplicates").status_code == 200
    admin_client.post("/api/auth/logout")
    assert client.get(f"/api/reports/{rid}/duplicates").status_code == 401
    # log admin back in for downstream fixtures
    admin_client.post("/api/auth/login", json={"email": "admin@test.et", "password": "admin-pass-123"})
