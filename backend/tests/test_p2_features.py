"""P2 completion features: web push, video_embedding analyzer, worker concurrency.

Push tests follow the platform rule: the API is deterministic; push delivery is
a bonus channel that must NEVER break requests when unconfigured or failing.
"""
import json

import pytest

from app.config import Settings, settings
from app.db import SessionLocal
from app.models import PushSubscription, Report, ReportMedia, User


# ---------------- push configuration gating ----------------

def test_push_disabled_returns_503(citizen_client):
    r = citizen_client.get("/api/push/vapid-public-key")
    assert r.status_code == 503
    r = citizen_client.post("/api/push/subscribe", json={
        "endpoint": "https://push.example.com/x", "p256dh": "k" * 20, "auth": "a" * 10})
    assert r.status_code == 503


def test_push_requires_auth(client):
    client.post("/api/auth/logout")
    r = client.post("/api/push/subscribe", json={
        "endpoint": "https://push.example.com/x", "p256dh": "k" * 20, "auth": "a" * 10})
    assert r.status_code == 401


def test_push_subscribe_roundtrip(citizen_client, monkeypatch):
    monkeypatch.setattr(settings, "vapid_public_key", "test-pub")
    monkeypatch.setattr(settings, "vapid_private_key", "test-priv")

    r = citizen_client.get("/api/push/vapid-public-key")
    assert r.status_code == 200 and r.json()["public_key"] == "test-pub"

    sub = {"endpoint": "https://push.example.com/e1", "p256dh": "k" * 20, "auth": "a" * 10}
    r = citizen_client.post("/api/push/subscribe", json=sub)
    assert r.status_code == 201 and r.json()["updated"] is False
    # idempotent re-subscribe updates keys instead of duplicating
    r = citizen_client.post("/api/push/subscribe", json={**sub, "auth": "b" * 10})
    assert r.status_code == 201 and r.json()["updated"] is True

    r = citizen_client.get("/api/push/status")
    assert r.json() == {"enabled": True, "devices": 1}

    r = citizen_client.request("DELETE", "/api/push/subscribe", json=sub)
    assert r.status_code == 200 and r.json()["removed"] == 1
    assert citizen_client.get("/api/push/status").json()["devices"] == 0


def test_push_isolation_between_users(citizen_client, monkeypatch):
    """A user must never see or delete another user's subscriptions."""
    monkeypatch.setattr(settings, "vapid_public_key", "p")
    monkeypatch.setattr(settings, "vapid_private_key", "s")
    db = SessionLocal()
    other = db.query(User).filter(User.email == "admin@test.et").first()
    db.add(PushSubscription(user_id=other.id, endpoint="https://push.example.com/other",
                            p256dh="x" * 20, auth="y" * 10))
    db.commit()
    db.close()
    # citizen deleting the admin's endpoint removes nothing
    r = citizen_client.request("DELETE", "/api/push/subscribe", json={
        "endpoint": "https://push.example.com/other", "p256dh": "x" * 20, "auth": "y" * 10})
    assert r.json()["removed"] == 0
    assert citizen_client.get("/api/push/status").json()["devices"] == 0


def test_send_push_noop_when_disabled():
    """notify() path: push must silently no-op without VAPID keys."""
    from app.push import send_push, push_enabled
    assert push_enabled() is False
    db = SessionLocal()
    user = db.query(User).first()
    assert send_push(db, user, "t", "b") == 0
    db.close()


def test_vapid_keygen():
    from app.push import generate_vapid_keys
    keys = generate_vapid_keys()
    assert set(keys) == {"public_key", "private_key"}
    # base64url, no padding; public key is a 65-byte uncompressed P-256 point
    import base64
    pub = base64.urlsafe_b64decode(keys["public_key"] + "==")
    assert len(pub) == 65 and pub[0] == 0x04


# ---------------- video_embedding duplicate analyzer ----------------

def _mk_report(db, title, sigs=None, lat=9.01, lng=38.76):
    r = Report(title=title, description="video dup test " + title,
               category="Roads & Transportation", latitude=lat, longitude=lng,
               city="Addis Ababa")
    db.add(r)
    db.commit()
    if sigs is not None:
        m = ReportMedia(report_id=r.id, kind="video", storage_key=f"t/{r.id}.mp4",
                        frame_sigs=json.dumps(sigs))
        db.add(m)
        db.commit()
    return r


def test_video_embedding_registered():
    from app.duplicates import get_analyzers
    names = [a.name for a in get_analyzers()]
    assert "video_embedding" in names


def test_video_embedding_matches_similar_frames():
    from app.duplicates import VideoEmbeddingAnalyzer
    db = SessionLocal()
    # same scene: signatures differ by a few bits per frame
    a = _mk_report(db, "video dup original", sigs=["ff00ff00ff00ff00", "aa55aa55aa55aa55"])
    b = _mk_report(db, "video dup rerecord", sigs=["ff00ff00ff00ff01", "aa55aa55aa55aa54"])
    cands = VideoEmbeddingAnalyzer().find(db, b)
    ids = [c.report.id for c in cands]
    assert a.id in ids
    top = next(c for c in cands if c.report.id == a.id)
    assert top.score >= 0.5 and top.analyzer == "video_embedding"
    assert "frame" in top.reason
    db.close()


def test_video_embedding_ignores_unrelated_videos():
    from app.duplicates import VideoEmbeddingAnalyzer
    db = SessionLocal()
    _mk_report(db, "video unrelated scene", sigs=["0000000000000000", "1111111111111111"])
    probe = _mk_report(db, "video probe", sigs=["ffffffffffffffff", "eeeeeeeeeeeeeeee"])
    cands = VideoEmbeddingAnalyzer().find(db, probe)
    titles = [c.report.title for c in cands]
    assert "video unrelated scene" not in titles
    db.close()


def test_video_embedding_no_sigs_no_crash():
    from app.duplicates import VideoEmbeddingAnalyzer
    db = SessionLocal()
    r = _mk_report(db, "video no media at all")
    assert VideoEmbeddingAnalyzer().find(db, r) == []
    db.close()


def test_duplicates_never_auto_delete():
    """Governing rule: analyzers only SURFACE candidates; both reports remain."""
    db = SessionLocal()
    a = _mk_report(db, "video keep original", sigs=["cc00cc00cc00cc00"])
    b = _mk_report(db, "video keep candidate", sigs=["cc00cc00cc00cc01"])
    from app.duplicates import find_duplicates
    find_duplicates(db, b)
    assert db.get(Report, a.id) is not None
    assert db.get(Report, b.id) is not None
    db.close()


# ---------------- worker concurrency setting ----------------

def test_worker_concurrency_setting():
    assert Settings().worker_concurrency == 2
    assert Settings(worker_concurrency=8).worker_concurrency == 8


def test_worker_module_uses_pool():
    import inspect
    from app import worker
    src = inspect.getsource(worker.main)
    assert "ThreadPoolExecutor" in src and "worker_concurrency" in str(
        inspect.getsource(worker)) or "concurrency" in src
