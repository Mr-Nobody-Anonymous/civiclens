"""P1 tests: org departments/invites/assignment/escalation, MFA + email
verification + session management, transparency portal, advanced search,
resolution quality, civic briefing."""
import json

from app.db import SessionLocal
from app.models import (Department, Organization, OrganizationUser, Report,
                        ReportStatus, Role, StaffInvite, User)
from tests.conftest import TestClient
from app.main import app


def _fresh(suffix, email=None):
    c = TestClient(app)
    c.post("/api/auth/register", json={
        "name": f"P1 {suffix}", "email": email or f"p1-{suffix}@test.et",
        "password": "p1-pass-12345"})
    return c


def _org(db, name="P1 Test Org"):
    org = db.query(Organization).filter_by(name=name).first()
    if not org:
        org = Organization(name=name, org_type="Test")
        db.add(org)
        db.commit()
    return org


# ================= departments + invites =================
def test_department_and_invite_flow(admin_client):
    db = SessionLocal()
    org = _org(db)
    oid = org.id
    db.close()

    # admin creates a department with geographic responsibility
    d = admin_client.post(f"/api/orgops/organizations/{oid}/departments", json={
        "name": "Bole District Team", "city": "Addis Ababa",
        "latitude": 8.99, "longitude": 38.79, "radius_m": 4000})
    assert d.status_code == 201
    # invite by email
    inv = admin_client.post(f"/api/orgops/organizations/{oid}/invites", json={
        "email": "p1-invitee@test.et", "org_role": "supervisor",
        "department_id": d.json()["id"]})
    assert inv.status_code == 201
    token = inv.json()["token"]

    # wrong user cannot accept
    wrong = _fresh("wronguser")
    assert wrong.post(f"/api/orgops/invites/{token}/accept").status_code == 403
    # right user accepts -> becomes org_staff supervisor in the department
    invitee = _fresh("invitee", email="p1-invitee@test.et")
    acc = invitee.post(f"/api/orgops/invites/{token}/accept")
    assert acc.status_code == 200 and acc.json()["org_role"] == "supervisor"
    # token single-use
    assert invitee.post(f"/api/orgops/invites/{token}/accept").status_code == 404

    db = SessionLocal()
    link = db.query(OrganizationUser).join(User).filter(
        User.email == "p1-invitee@test.et").first()
    assert link.org_role == "supervisor" and link.department_id == d.json()["id"]
    db.close()

    # departments list shows workload fields
    lst = invitee.get(f"/api/orgops/organizations/{oid}/departments")
    assert lst.status_code == 200
    assert lst.json()[0]["members"] == 1


def test_department_requires_manager(citizen_client):
    db = SessionLocal()
    oid = _org(db).id
    db.close()
    assert citizen_client.post(f"/api/orgops/organizations/{oid}/departments",
                               json={"name": "Rogue Dept"}).status_code == 403


# ================= assignment recommendation =================
def test_assignment_recommendation_ranks_geo_and_workload(admin_client):
    db = SessionLocal()
    org = _org(db, "P1 Assign Org")
    dept = Department(organization_id=org.id, name="Near Team",
                      latitude=9.015, longitude=38.76, radius_m=3000)
    db.add(dept); db.commit()
    near = User(name="Near Staff", email="p1-near@test.et", role=Role.org_staff,
                password_hash="x")
    far = User(name="Far Staff", email="p1-far@test.et", role=Role.org_staff,
               password_hash="x")
    db.add_all([near, far]); db.commit()
    db.add(OrganizationUser(organization_id=org.id, user_id=near.id, department_id=dept.id))
    db.add(OrganizationUser(organization_id=org.id, user_id=far.id))
    db.commit()

    rpt = Report(title="Assignment rec test", description="near the geofence",
                 city="Addis Ababa", latitude=9.016, longitude=38.761,
                 organization_id=org.id, status=ReportStatus.assigned)
    db.add(rpt); db.commit()
    oid, rid = org.id, rpt.id
    db.close()

    rec = admin_client.get(f"/api/orgops/organizations/{oid}/assignment-recommendation"
                           f"?report_id={rid}")
    assert rec.status_code == 200
    data = rec.json()
    assert "advisory" in data["advisory"].lower() or "supervisor" in data["advisory"]
    top = data["recommendations"][0]
    assert top["name"] == "Near Staff" and top["geo_match"] is True


# ================= MFA + email verification + sessions =================
def test_mfa_full_cycle(client):
    u = _fresh("mfa")
    setup = u.post("/api/security/mfa/setup").json()
    secret = setup["secret"]
    assert "otpauth://totp" in setup["otpauth_uri"]

    from app.routers.security2 import totp_now
    # wrong code rejected
    assert u.post("/api/security/mfa/enable", json={"code": "000000"}).status_code == 401
    en = u.post("/api/security/mfa/enable", json={"code": totp_now(secret)})
    assert en.status_code == 200
    backup_codes = en.json()["backup_codes"]
    assert len(backup_codes) == 8

    # login now requires MFA: no code -> 428, wrong -> 401, TOTP -> 200
    u.post("/api/auth/logout")
    r = u.post("/api/auth/login", json={"email": "p1-mfa@test.et", "password": "p1-pass-12345"})
    assert r.status_code == 428
    r = u.post("/api/auth/login", json={"email": "p1-mfa@test.et",
                                        "password": "p1-pass-12345", "mfa_code": "111111"})
    assert r.status_code == 401
    r = u.post("/api/auth/login", json={"email": "p1-mfa@test.et",
                                        "password": "p1-pass-12345",
                                        "mfa_code": totp_now(secret)})
    assert r.status_code == 200

    # backup code works exactly once
    u.post("/api/auth/logout")
    r = u.post("/api/auth/login", json={"email": "p1-mfa@test.et",
                                        "password": "p1-pass-12345",
                                        "mfa_code": backup_codes[0]})
    assert r.status_code == 200
    u.post("/api/auth/logout")
    r = u.post("/api/auth/login", json={"email": "p1-mfa@test.et",
                                        "password": "p1-pass-12345",
                                        "mfa_code": backup_codes[0]})
    assert r.status_code == 401   # single use


def test_email_verification_flow(client):
    u = _fresh("everify")
    assert u.post("/api/security/verify-email/request").status_code == 200
    db = SessionLocal()
    from app.models import EmailToken
    me = u.get("/api/auth/me").json()
    tok = db.query(EmailToken).filter_by(user_id=me["id"]).first()
    db.close()
    assert u.post("/api/security/verify-email/confirm",
                  json={"token": "garbage"}).status_code == 400
    ok = u.post("/api/security/verify-email/confirm", json={"token": tok.token})
    assert ok.status_code == 200 and ok.json()["email_verified"] is True
    # token single use
    assert u.post("/api/security/verify-email/confirm",
                  json={"token": tok.token}).status_code == 400


def test_session_management(client):
    u = _fresh("sessions")
    u2 = TestClient(app)
    u2.post("/api/auth/login", json={"email": "p1-sessions@test.et", "password": "p1-pass-12345"})
    sessions = u.get("/api/security/sessions").json()
    assert len(sessions) >= 2
    other = next(s for s in sessions if not s["current"])
    assert u.delete(f"/api/security/sessions/{other['full_id_prefix']}").status_code == 200
    assert u2.get("/api/auth/me").json() is None      # revoked device logged out
    assert u.get("/api/auth/me").json() is not None   # own session intact


# ================= transparency + search + quality + briefing =================
def test_transparency_public_and_private_safe(client):
    t = client.get("/api/transparency").json()
    assert t["reports"] >= 1 and "organization_performance" in t
    assert "privacy_note" in t
    blob = json.dumps(t)
    assert "@" not in blob.replace("privacy_note", "")   # no emails anywhere
    assert "reporter" not in blob


def test_advanced_search_filters(admin_client, client):
    r = admin_client.post("/api/reports", json={
        "title": "Search filter target zq7", "description": "unique searchable description zq7.",
        "category": "Water", "city": "Gondar", "latitude": 12.6, "longitude": 37.46})
    assert r.status_code == 201
    out = client.get("/api/search?q=zq7&category=Water&city=Gondar").json()
    assert out["total"] == 1
    out = client.get("/api/search?q=zq7&city=Adama").json()
    assert out["total"] == 0
    # geographic radius filter
    out = client.get("/api/search?lat=12.6&lng=37.46&radius_m=2000&category=Water").json()
    assert out["total"] >= 1
    # SLA filter is staff-only (use a genuinely anonymous client)
    anon = TestClient(app)
    assert anon.get("/api/search?sla=breached").status_code == 403
    assert admin_client.get("/api/search?sla=breached").status_code == 200


def test_saved_searches(client):
    u = _fresh("saved")
    s = u.post("/api/saved-searches", json={
        "label": "Bole roads", "params": {"category": "Roads & Transportation", "city": "Addis Ababa"}})
    assert s.status_code == 201
    lst = u.get("/api/saved-searches").json()
    assert lst[0]["name"] == "Bole roads"
    assert lst[0]["params"]["category"] == "Roads & Transportation"


def test_resolution_quality_advisory(admin_client):
    db = SessionLocal()
    org = _org(db, "P1 Quality Org")
    r = Report(title="Quality sample", description="resolved with everything",
               organization_id=org.id, status=ReportStatus.resolved,
               resolution_confirmed=True, resolution_check_score=0.85)
    db.add(r); db.commit()
    oid = org.id
    db.close()
    q = admin_client.get(f"/api/organizations/{oid}/resolution-quality").json()
    assert q["sample"] == 1 and q["citizen_confirmed"] == 1
    assert 0 <= q["resolution_quality_advisory"] <= 1
    assert "Advisory only" in q["advisory_note"]


def test_civic_briefing(admin_client, client):
    b = admin_client.get("/api/intelligence/briefing").json()
    assert set(b["kpis"]) >= {"critical_emerging", "new_reports_week", "sla_breaches_week",
                              "reopened_issues", "citizens_engaged_week"}
    assert b["advisory_label"] == "AI-generated advisory. Human decision required."
    assert isinstance(b["advisory"], str) and len(b["advisory"]) > 10
    # staff-only (genuinely anonymous client)
    anon = TestClient(app)
    assert anon.get("/api/intelligence/briefing").status_code == 401
