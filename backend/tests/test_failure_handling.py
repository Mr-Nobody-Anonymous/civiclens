"""Failure-matrix tests: storage unavailable and SMTP unavailable."""
import io

from app.db import SessionLocal
from app.models import Notification, User


def test_storage_failure_gives_clear_upload_error(client, admin_client, monkeypatch):
    """Storage backend down -> upload returns a 500-class error, report survives."""
    r = admin_client.post("/api/reports", json={
        "title": "Storage failure test", "description": "Testing storage outage behaviour here.",
        "category": "Water", "city": "Addis Ababa"})
    rid = r.json()["id"]

    from app.routers import reports as reports_mod

    def broken_save(key, stream):
        raise OSError("disk full / storage unreachable")

    monkeypatch.setattr(reports_mod.storage, "save", broken_save)
    png = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 200)
    resp = admin_client.post(f"/api/reports/{rid}/media",
                             files={"file": ("x.png", png, "image/png")})
    assert resp.status_code == 500
    body = resp.json()
    assert "Internal server error" in body["detail"]   # no stack trace leaked
    assert "request_id" in body

    # report itself is intact and still visible
    detail = admin_client.get(f"/api/reports/{rid}").json()
    assert detail["status"] == "submitted"
    assert detail["media"] == []

    # storage restored (monkeypatch reverts) -> retry succeeds
    monkeypatch.undo()
    png2 = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"1" * 200)
    resp2 = admin_client.post(f"/api/reports/{rid}/media",
                              files={"file": ("x.png", png2, "image/png")})
    assert resp2.status_code == 201


def test_smtp_failure_never_breaks_request_and_keeps_inapp(client, monkeypatch):
    """SMTP down -> request still succeeds, in-app notification still created,
    send is attempted twice (retry) then dropped without raising."""
    from app import notify as notify_mod

    attempts = {"n": 0}

    class BrokenSmtp:
        def send(self, user, title, body):
            attempts["n"] += 1
            raise ConnectionError("SMTP unreachable")

    monkeypatch.setattr(notify_mod, "_email_channel", lambda: BrokenSmtp())

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email="cit@test.et").first()
        before = db.query(Notification).filter_by(user_id=user.id).count()
        # must not raise despite the SMTP failure
        notify_mod.notify(db, user, "test", "SMTP failure test", "body text")
        after = db.query(Notification).filter_by(user_id=user.id).count()
        assert after == before + 1          # in-app notification persisted
        assert attempts["n"] == 2           # initial attempt + one retry
    finally:
        db.close()
