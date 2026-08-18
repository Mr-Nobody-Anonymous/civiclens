"""Phase C tests: subscriptions, community verification, geographic routing,
notification preferences, city intelligence, Amharic AI (service-level tests
live in ai-service/)."""
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import (CommunityVote, Organization, OrganizationRule, Report,
                        ReportStatus, Subscription, User)
from tests.conftest import TestClient
from app.main import app


def _fresh(suffix):
    c = TestClient(app)
    c.post("/api/auth/register", json={
        "name": f"PC {suffix}", "email": f"pc-{suffix}@test.et", "password": "pc-pass-12345"})
    return c


def _mk(client, title="Phase C report", lat=9.01, lng=38.76, cat="Water", **over):
    body = {"title": title, "description": "A long enough description of this civic issue.",
            "category": cat, "city": "Addis Ababa", "latitude": lat, "longitude": lng}
    body.update(over)
    r = client.post("/api/reports", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------- subscriptions ----------------
def test_subscribe_and_area_fanout(admin_client):
    follower = _fresh("follower")
    # follow an area around a point
    resp = follower.post("/api/subscriptions", json={
        "target_type": "area", "latitude": 9.30, "longitude": 38.80,
        "radius_m": 2000, "label": "My neighborhood"})
    assert resp.status_code == 201
    # duplicate subscribe is idempotent
    again = follower.post("/api/subscriptions", json={
        "target_type": "area", "latitude": 9.30, "longitude": 38.80, "radius_m": 2000})
    assert again.json().get("already") is True

    # a report lands inside the area -> fan-out notifies the follower
    rpt = _mk(admin_client, title="Fanout area test", lat=9.301, lng=38.801)
    db = SessionLocal()
    from app.routers.community import notify_subscribers
    r = db.get(Report, rpt["id"])
    r.category = "Water"
    db.commit()
    notify_subscribers(db, r)
    db.close()
    notes = follower.get("/api/notifications").json()
    assert any(n["kind"] == "followed_update" for n in notes)

    # list + unsubscribe
    subs = follower.get("/api/subscriptions").json()
    assert len(subs) == 1
    assert follower.delete(f"/api/subscriptions/{subs[0]['id']}").status_code == 200
    assert follower.get("/api/subscriptions").json() == []


def test_category_subscription_fanout(admin_client):
    follower = _fresh("catfollow")
    follower.post("/api/subscriptions", json={"target_type": "category", "target_id": "Telecom"})
    rpt = _mk(admin_client, title="Telecom fanout test", cat="Telecom", lat=8.5, lng=39.2)
    db = SessionLocal()
    from app.routers.community import notify_subscribers
    r = db.get(Report, rpt["id"])
    r.category = "Telecom"
    db.commit()
    notify_subscribers(db, r)
    db.close()
    notes = follower.get("/api/notifications").json()
    assert any("Telecom" in (n["body"] or "") or n["kind"] == "followed_update" for n in notes)


def test_subscription_requires_auth(client):
    assert client.post("/api/subscriptions", json={
        "target_type": "category", "target_id": "Water"}).status_code == 401


# ---------------- community verification ----------------
def test_one_vote_per_user_and_no_self_vote(admin_client):
    rpt = _mk(admin_client, title="Community vote test")
    db = SessionLocal()
    r = db.get(Report, rpt["id"])
    r.status = ReportStatus.assigned
    db.commit(); db.close()

    voter = _fresh("voter1")
    # reporter (admin) cannot vote on own report
    self_vote = admin_client.post(f"/api/reports/{rpt['id']}/verify", json={"vote": "still_exists"})
    assert self_vote.status_code == 422
    # voter votes; changing their mind updates, never duplicates
    assert voter.post(f"/api/reports/{rpt['id']}/verify", json={"vote": "still_exists"}).status_code == 200
    assert voter.post(f"/api/reports/{rpt['id']}/verify", json={"vote": "resolved"}).status_code == 200
    db = SessionLocal()
    assert db.query(CommunityVote).filter_by(report_id=rpt["id"]).count() == 1
    db.close()
    # aggregation is anonymous and correct
    summary = voter.get(f"/api/reports/{rpt['id']}/verification").json()
    assert summary["resolved"] == 1 and summary["still_exists"] == 0
    assert summary["my_vote"] == "resolved"
    assert "authority" in summary["note"]


def test_votes_never_change_status(admin_client):
    """Votes are evidence, not authority — status must not move."""
    rpt = _mk(admin_client, title="Vote authority test")
    db = SessionLocal()
    r = db.get(Report, rpt["id"])
    r.status = ReportStatus.in_progress
    db.commit(); db.close()
    for i in range(3):
        _fresh(f"mob{i}").post(f"/api/reports/{rpt['id']}/verify", json={"vote": "resolved"})
    db = SessionLocal()
    assert db.get(Report, rpt["id"]).status == ReportStatus.in_progress
    db.close()


# ---------------- geographic routing ----------------
def test_geofenced_rule_beats_city_rule(client):
    db = SessionLocal()
    org_city = Organization(name="City Roads HQ Test", org_type="Roads")
    org_bole = Organization(name="Bole District Roads Team Test", org_type="Roads")
    db.add_all([org_city, org_bole]); db.commit()
    db.add(OrganizationRule(category="Roads & Transportation", organization_id=org_city.id,
                            city="Addis Ababa", priority=10))
    db.add(OrganizationRule(category="Roads & Transportation", organization_id=org_bole.id,
                            city="Addis Ababa", priority=10,
                            latitude=8.995, longitude=38.788, radius_m=3000))
    db.commit()

    from app.routing import route_report
    # inside the Bole geofence -> district team wins
    inside = Report(title="pothole", description="pothole", city="Addis Ababa",
                    latitude=8.996, longitude=38.789)
    org, rule = route_report(db, inside, "Roads & Transportation", "pothole on road")
    assert org.name == "Bole District Roads Team Test"
    # outside the geofence -> city-wide org
    outside = Report(title="pothole", description="pothole", city="Addis Ababa",
                     latitude=9.06, longitude=38.72)
    org2, _ = route_report(db, outside, "Roads & Transportation", "pothole on road")
    assert org2.name != "Bole District Roads Team Test"
    # cleanup: deactivate the test rules so they don't interfere with other tests
    for rule in db.query(OrganizationRule).filter(
            OrganizationRule.organization_id.in_([org_city.id, org_bole.id])).all():
        rule.is_active = False
    db.commit()
    db.close()


def test_geo_rule_skipped_without_coordinates(client):
    db = SessionLocal()
    from app.routing import route_report
    no_coords = Report(title="pothole", description="pothole", city="Addis Ababa")
    org, rule = route_report(db, no_coords, "Roads & Transportation", "pothole")
    assert org is not None          # falls back to non-geo rules, never lost
    assert rule.radius_m is None
    db.close()


# ---------------- notification preferences ----------------
def test_prefs_respected_by_notify(client):
    u = _fresh("prefs")
    me = u.get("/api/auth/me").json()
    # defaults on
    prefs = u.get("/api/notification-preferences").json()
    assert prefs["resolution"] is True
    # switch resolution off
    u.put("/api/notification-preferences", json={"prefs": {**prefs, "resolution": False}})
    db = SessionLocal()
    from app.notify import notify
    user = db.get(User, me["id"])
    before = len(u.get("/api/notifications").json())
    notify(db, user, "resolved", "Should be suppressed", "")
    notify(db, user, "assigned", "Should arrive", "")
    db.close()
    notes = u.get("/api/notifications").json()
    titles = [n["title"] for n in notes]
    assert "Should arrive" in titles
    assert "Should be suppressed" not in titles


def test_prefs_ignore_unknown_keys(client):
    u = _fresh("prefsjunk")
    out = u.put("/api/notification-preferences", json={"prefs": {"hack": True, "resolution": False}}).json()
    assert "hack" not in out and out["resolution"] is False


# ---------------- city intelligence ----------------
def test_hotspots_and_trends(admin_client):
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    # seed 6 reports in one ~1km cell: 2 older, 4 recent -> +100% trend
    for i in range(6):
        r = Report(title=f"Hotspot seed {i}", description="hotspot test seed report",
                   category="Roads & Transportation", city="Hawassa",
                   latitude=7.0500 + i * 0.0004, longitude=38.4760,
                   created_at=now - timedelta(days=25 if i < 2 else 2))
        db.add(r)
    db.commit(); db.close()

    resp = admin_client.get("/api/intelligence/overview?city=Hawassa")
    assert resp.status_code == 200
    data = resp.json()
    assert data["city"] == "Hawassa"
    hs = [h for h in data["hotspots"] if h["top_category"] == "Roads & Transportation"]
    assert hs and hs[0]["count"] >= 6
    assert hs[0]["trend_pct"] is not None and hs[0]["trend_pct"] > 0
    assert "advisory" in hs[0]
    assert "Authorities review" in data["advisory_note"]


def test_intelligence_overview_staff_only(client):
    assert client.get("/api/intelligence/overview").status_code == 401
    # public hotspots endpoint IS open (coarse coordinates only)
    assert client.get("/api/intelligence/hotspots").status_code == 200
