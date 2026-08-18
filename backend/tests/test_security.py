"""Security-focused tests: CSRF, lockout, sessions, IDOR, media authz, org isolation."""
import io

from app.db import SessionLocal
from app.models import Organization, OrganizationUser, Role, User
from app.security import hash_password


def _report(client, **over):
    body = {"title": "Security test report", "description": "A description long enough to pass validation.",
            "category": "Roads & Transportation", "city": "Addis Ababa",
            "latitude": 9.01, "longitude": 38.76,
            "captcha_a": 1, "captcha_b": 1, "captcha_answer": 2}
    body.update(over)
    return client.post("/api/reports", json=body)


# ---------------- CSRF ----------------
def test_csrf_required_for_authenticated_mutations(client):
    client.post("/api/auth/login", json={"email": "admin@test.et", "password": "admin-pass-123"})
    r = client.post("/api/reports/some-id/flag", json={"reason": "x"},
                    headers={"X-CSRF-Token": "wrong-token"})
    assert r.status_code == 403
    assert "CSRF" in r.json()["detail"]
    # correct token (auto-injected by conftest client) reaches the handler (404: no such report)
    r = client.post("/api/reports/some-id/flag", json={"reason": "test reason"})
    assert r.status_code == 404
    client.post("/api/auth/logout")


def test_csrf_not_required_for_login(client):
    r = client.post("/api/auth/login", json={"email": "admin@test.et", "password": "wrong"},
                    headers={"X-CSRF-Token": ""})
    assert r.status_code == 401  # got through CSRF to auth check


# ---------------- lockout ----------------
def test_login_lockout_after_repeated_failures(client):
    db = SessionLocal()
    u = User(name="Lock Me", email="lockme@test.et", role=Role.citizen,
             password_hash=hash_password("correct-password"))
    db.add(u)
    db.commit()
    db.close()
    for _ in range(8):
        client.post("/api/auth/login", json={"email": "lockme@test.et", "password": "bad"})
    r = client.post("/api/auth/login", json={"email": "lockme@test.et", "password": "correct-password"})
    assert r.status_code == 429  # locked even with the right password


# ---------------- password change / sessions ----------------
def test_password_change_revokes_other_sessions(client):
    client.post("/api/auth/register", json={
        "name": "PW User", "email": "pw@test.et", "password": "first-password1"})
    # second session in another client
    from tests.conftest import TestClient
    from app.main import app
    other = TestClient(app)
    other.post("/api/auth/login", json={"email": "pw@test.et", "password": "first-password1"})
    assert other.get("/api/auth/me").json()["email"] == "pw@test.et"

    r = client.post("/api/auth/change-password", json={
        "current_password": "first-password1", "new_password": "second-password2"})
    assert r.status_code == 200
    # other session is dead; current one survives
    assert other.get("/api/auth/me").json() is None
    assert client.get("/api/auth/me").json()["email"] == "pw@test.et"
    client.post("/api/auth/logout")


def test_password_reset_flow(client):
    client.post("/api/auth/forgot-password", json={"email": "pw@test.et"})
    db = SessionLocal()
    from app.models import PasswordReset
    pr = db.query(PasswordReset).order_by(PasswordReset.created_at.desc()).first()
    db.close()
    assert pr is not None
    r = client.post("/api/auth/reset-password", json={"token": pr.token, "new_password": "third-password3"})
    assert r.status_code == 200
    # token single-use
    r = client.post("/api/auth/reset-password", json={"token": pr.token, "new_password": "fourth-password4"})
    assert r.status_code == 400
    r = client.post("/api/auth/login", json={"email": "pw@test.et", "password": "third-password3"})
    assert r.status_code == 200
    client.post("/api/auth/logout")


def test_forgot_password_no_account_enumeration(client):
    r = client.post("/api/auth/forgot-password", json={"email": "who@nowhere.et"})
    assert r.status_code == 200 and r.json()["ok"] is True


# ---------------- org isolation / IDOR ----------------
def _mk_org_user(name, email, orgname):
    db = SessionLocal()
    org = db.query(Organization).filter_by(name=orgname).first()
    if not org:
        org = Organization(name=orgname, org_type="Test")
        db.add(org)
        db.commit()
    u = db.query(User).filter_by(email=email).first()
    if not u:
        u = User(name=name, email=email, role=Role.org_staff,
                 password_hash=hash_password("org-password1"))
        db.add(u)
        db.commit()
        db.add(OrganizationUser(organization_id=org.id, user_id=u.id))
        db.commit()
    oid = org.id
    db.close()
    return oid


def test_org_cannot_access_other_orgs_reports(client, admin_client):
    org_a = _mk_org_user("Org A Staff", "orga@test.et", "Org Alpha")
    org_b = _mk_org_user("Org B Staff", "orgb@test.et", "Org Beta")

    rid = _report(admin_client).json()["id"]
    admin_client.patch(f"/api/reports/{rid}/assignment", json={"organization_id": org_a})
    admin_client.post("/api/auth/logout")

    # Org B staff must not see or manage Org A's report
    client.post("/api/auth/login", json={"email": "orgb@test.et", "password": "org-password1"})
    rows = client.get("/api/dashboard/org-reports").json()
    assert rid not in [r["id"] for r in rows]
    r = client.patch(f"/api/reports/{rid}/status", json={"status": "in_progress"})
    assert r.status_code == 403
    # priority queue: only own org
    pq = client.get("/api/reports/priority").json()
    assert rid not in [r["id"] for r in pq]
    client.post("/api/auth/logout")

    # Org A staff CAN manage it
    client.post("/api/auth/login", json={"email": "orga@test.et", "password": "org-password1"})
    rows = client.get("/api/dashboard/org-reports").json()
    assert rid in [r["id"] for r in rows]
    client.post("/api/auth/logout")


def test_citizen_cannot_use_admin_endpoints(citizen_client):
    assert citizen_client.get("/api/admin/users").status_code == 403
    assert citizen_client.get("/api/admin/jobs").status_code == 403
    assert citizen_client.get("/api/audit-logs").status_code == 403
    assert citizen_client.post("/api/organizations", json={"name": "Rogue Org"}).status_code == 403


def test_flagged_media_unauthorized_access(client, admin_client):
    """Media on flagged (hidden) reports must not be served to strangers."""
    rid = _report(admin_client).json()["id"]
    png = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 200)
    up = admin_client.post(f"/api/reports/{rid}/media",
                           files={"file": ("ev.png", png, "image/png")})
    assert up.status_code == 201
    mid = up.json()["id"]
    admin_client.post(f"/api/reports/{rid}/flag", json={"reason": "hide for test"})
    admin_client.post("/api/auth/logout")

    # anonymous: no
    assert client.get(f"/api/reports/{rid}/media/{mid}/file").status_code == 403
    # unrelated citizen: no
    client.post("/api/auth/login", json={"email": "cit@test.et", "password": "citizen-pass-1"})
    assert client.get(f"/api/reports/{rid}/media/{mid}/file").status_code == 403
    client.post("/api/auth/logout")
    # unrelated org staff: no
    client.post("/api/auth/login", json={"email": "orgb@test.et", "password": "org-password1"})
    assert client.get(f"/api/reports/{rid}/media/{mid}/file").status_code == 403
    client.post("/api/auth/logout")
    # admin: yes
    client.post("/api/auth/login", json={"email": "admin@test.et", "password": "admin-pass-123"})
    assert client.get(f"/api/reports/{rid}/media/{mid}/file").status_code == 200
    client.patch(f"/api/reports/{rid}/unflag")
    client.post("/api/auth/logout")


def test_admin_cannot_demote_self(admin_client):
    me = admin_client.get("/api/auth/me").json()
    r = admin_client.patch(f"/api/admin/users/{me['id']}/role", json={"role": "citizen"})
    assert r.status_code == 422
