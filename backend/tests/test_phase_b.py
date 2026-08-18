"""Phase B tests: resolution verification, moderation center, resumable
uploads, offline idempotency. Includes authorization + failure modes."""
import hashlib
import io

from tests.conftest import TestClient
from app.main import app


def _fresh_citizen(suffix: str):
    """Independent client with its own cookie jar (fixtures share one jar)."""
    c = TestClient(app)
    c.post("/api/auth/register", json={
        "name": f"PB {suffix}", "email": f"pb-{suffix}@test.et", "password": "pb-pass-12345"})
    return c

from app.db import SessionLocal
from app.models import Report, ReportComment, ReportMedia, ReportStatus, UploadSession

PNG = b"\x89PNG\r\n\x1a\n"


def _mk(client, title="Phase B report", cat="Roads & Transportation", **over):
    body = {"title": title, "description": "A long enough description of this civic issue.",
            "category": cat, "city": "Addis Ababa", "latitude": 9.01, "longitude": 38.76,
            "captcha_a": 1, "captcha_b": 1, "captcha_answer": 2}
    body.update(over)
    return client.post("/api/reports", json=body).json()


def _to_status(db, rid, status):
    r = db.get(Report, rid)
    r.status = ReportStatus(status)
    db.commit()
    return r


# ================= resolution verification =================
def test_resolve_requires_evidence_for_physical_categories(admin_client):
    r = _mk(admin_client, title="Evidence gate test")
    db = SessionLocal()
    rpt = _to_status(db, r["id"], "in_progress")
    rpt.category = "Roads & Transportation"
    db.commit(); db.close()
    # no resolution evidence + no override note -> 422 (even for admin without note)
    resp = admin_client.patch(f"/api/reports/{r['id']}/status", json={"status": "resolved"})
    assert resp.status_code == 422
    assert "resolution evidence" in resp.json()["detail"]
    # admin override WITH a written reason is allowed (audited)
    resp = admin_client.patch(f"/api/reports/{r['id']}/status",
                              json={"status": "resolved", "note": "Verified on site personally"})
    assert resp.status_code == 200


def test_resolve_with_evidence_passes_gate(admin_client):
    r = _mk(admin_client, title="Evidence upload gate test")
    db = SessionLocal()
    rpt = _to_status(db, r["id"], "in_progress")
    rpt.category = "Water"
    db.commit(); db.close()
    up = admin_client.post(f"/api/reports/{r['id']}/media", data={"kind": "resolution"},
                           files={"file": ("fixed.png", io.BytesIO(PNG + b"fix" * 60), "image/png")})
    assert up.status_code == 201
    resp = admin_client.patch(f"/api/reports/{r['id']}/status", json={"status": "resolved"})
    assert resp.status_code == 200


def test_citizen_confirm_and_dispute(admin_client):
    reporter = _fresh_citizen("confirm")
    stranger = _fresh_citizen("stranger")
    r = reporter.post("/api/reports", json={
        "title": "Confirm resolution test", "description": "Testing citizen confirmation flow here.",
        "category": "Other", "city": "Adama"}).json()
    db = SessionLocal(); _to_status(db, r["id"], "resolved"); db.close()
    # a stranger cannot confirm
    resp = stranger.post(f"/api/reports/{r['id']}/confirm-resolution?confirmed=true")
    assert resp.status_code == 403
    # reporter disputes -> reopened via state machine
    resp = reporter.post(f"/api/reports/{r['id']}/confirm-resolution?confirmed=false")
    assert resp.status_code == 200 and resp.json()["status"] == "reopened"
    # cannot confirm when not resolved
    resp = reporter.post(f"/api/reports/{r['id']}/confirm-resolution?confirmed=true")
    assert resp.status_code == 409


def _real_png(seed: int = 0) -> bytes:
    """A real decodable PNG (so thumbnails + perceptual hashes actually compute)."""
    from PIL import Image
    import random
    rng = random.Random(seed)
    img = Image.new("RGB", (64, 64))
    img.putdata([(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
                 for _ in range(64 * 64)])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_advisory_identical_resolution_evidence_flags_review(admin_client):
    """Identical before/after images -> low advisory score -> review queued.
    Advisory NEVER changes status by itself."""
    r = _mk(admin_client, title="Advisory identical test")
    payload = _real_png(seed=42)
    assert admin_client.post(f"/api/reports/{r['id']}/media",
        files={"file": ("before.png", io.BytesIO(payload), "image/png")}).status_code == 201
    assert admin_client.post(f"/api/reports/{r['id']}/media", data={"kind": "resolution"},
        files={"file": ("after.png", io.BytesIO(payload), "image/png")}).status_code == 201
    db = SessionLocal()
    rpt = db.get(Report, r["id"])
    assert rpt.resolution_check_score is not None and rpt.resolution_check_score < 0.6
    assert "identical" in (rpt.resolution_check_notes or "")
    from app.models import AIReview
    assert db.query(AIReview).filter_by(report_id=r["id"], reason="resolution_check").count() == 1
    assert rpt.status == ReportStatus.submitted   # advisory did NOT touch status
    db.close()


# ================= moderation center =================
def test_unified_queue_combines_sources(admin_client):
    r = _mk(admin_client, title="Mod queue combo test")
    admin_client.post(f"/api/reports/{r['id']}/flag", json={"reason": "spam test"})
    c = admin_client.post(f"/api/reports/{r['id']}/comments", json={"body": "abusive text here"})
    cid = c.json()["id"]
    admin_client.post(f"/api/moderation/comments/{cid}/flag")

    q = admin_client.get("/api/moderation/queue").json()
    kinds = {i["kind"] for i in q["items"]}
    assert "flagged_report" in kinds and "flagged_comment" in kinds
    assert q["counts"]["total"] >= 2
    # severity-first ordering holds
    sevs = [i.get("severity") or 0 for i in q["items"]]
    assert sevs == sorted(sevs, reverse=True)
    admin_client.patch(f"/api/reports/{r['id']}/unflag")


def test_comment_hide_is_reversible_and_public_hidden(admin_client, client):
    r = _mk(admin_client, title="Hide comment test")
    cid = admin_client.post(f"/api/reports/{r['id']}/comments", json={"body": "to be hidden"}).json()["id"]
    assert admin_client.post(f"/api/moderation/comments/{cid}/hide",
                             json={"hidden": True, "reason": "test"}).status_code == 200
    # public no longer sees it
    admin_client.post("/api/auth/logout")
    pub = client.get(f"/api/reports/{r['id']}").json()
    assert all(c["id"] != cid for c in pub["comments"])
    admin_client.post("/api/auth/login", json={"email": "admin@test.et", "password": "admin-pass-123"})
    # restore
    assert admin_client.post(f"/api/moderation/comments/{cid}/hide",
                             json={"hidden": False}).status_code == 200
    db = SessionLocal()
    c = db.get(ReportComment, cid)
    assert c.hidden is False and c.is_flagged is False
    db.close()


def test_moderation_authz(citizen_client):
    assert citizen_client.get("/api/moderation/queue").status_code == 403
    assert citizen_client.post("/api/moderation/comments/x/hide",
                               json={"hidden": True}).status_code == 403
    assert citizen_client.post("/api/moderation/bulk",
                               json={"ids": ["x"], "action": "unflag_reports"}).status_code == 403


def test_bulk_rejects_unsafe_actions(admin_client):
    resp = admin_client.post("/api/moderation/bulk",
                             json={"ids": ["a"], "action": "delete_reports"})
    assert resp.status_code == 422
    resp = admin_client.post("/api/moderation/bulk",
                             json={"ids": ["x"] * 51, "action": "unflag_reports"})
    assert resp.status_code == 422


# ================= resumable uploads =================
def _chunked_upload(client, rid, payload, ctype="image/png", declare_sha=True, chunk=None):
    sha = hashlib.sha256(payload).hexdigest() if declare_sha else None
    sess = client.post("/api/uploads", json={
        "report_id": rid, "filename": "chunked.png", "content_type": ctype,
        "total_size": len(payload), "sha256": sha}).json()
    uid, csize = sess["upload_id"], sess["chunk_size"]
    for i in range(sess["total_chunks"]):
        if chunk is not None and i == chunk:
            continue   # simulate interruption: skip this chunk
        r = client.put(f"/api/uploads/{uid}/chunks/{i}",
                       content=payload[i*csize:(i+1)*csize])
        assert r.status_code == 200
    return uid, sess


def test_chunked_upload_end_to_end(admin_client):
    r = _mk(admin_client, title="Chunked upload test")
    payload = PNG + b"C" * (3 * 1024 * 1024)      # 3MB -> 2 chunks
    uid, sess = _chunked_upload(admin_client, r["id"], payload)
    assert sess["total_chunks"] == 2
    done = admin_client.post(f"/api/uploads/{uid}/complete")
    assert done.status_code == 200
    body = done.json()
    assert body["media"]["kind"] == "image"
    assert body["sha256"] == hashlib.sha256(payload).hexdigest()
    # idempotent completion
    assert admin_client.post(f"/api/uploads/{uid}/complete").json().get("already") is True
    # media went through the normal pipeline (sha recorded)
    db = SessionLocal()
    m = db.query(ReportMedia).filter_by(report_id=r["id"]).first()
    assert m.sha256 == body["sha256"]
    db.close()


def test_chunked_upload_resume_after_interruption(admin_client):
    r = _mk(admin_client, title="Resume upload test")
    payload = PNG + b"R" * (3 * 1024 * 1024)
    uid, _ = _chunked_upload(admin_client, r["id"], payload, chunk=1)  # chunk 1 "lost"
    # complete fails listing the missing chunk
    resp = admin_client.post(f"/api/uploads/{uid}/complete")
    assert resp.status_code == 409 and "Missing chunks" in resp.json()["detail"]
    # resume info tells the client exactly what to re-send
    info = admin_client.get(f"/api/uploads/{uid}").json()
    assert info["missing"] == [1]
    # re-send chunk 1 (also verifies chunk re-PUT idempotency), then complete
    csize = info["chunk_size"]
    admin_client.put(f"/api/uploads/{uid}/chunks/1", content=payload[csize:2*csize])
    admin_client.put(f"/api/uploads/{uid}/chunks/1", content=payload[csize:2*csize])
    assert admin_client.post(f"/api/uploads/{uid}/complete").status_code == 200


def test_chunked_upload_checksum_mismatch_rejected(admin_client):
    r = _mk(admin_client, title="Checksum mismatch test")
    payload = PNG + b"X" * (1024 * 100)
    sess = admin_client.post("/api/uploads", json={
        "report_id": r["id"], "filename": "x.png", "content_type": "image/png",
        "total_size": len(payload), "sha256": "0" * 64}).json()
    admin_client.put(f"/api/uploads/{sess['upload_id']}/chunks/0", content=payload)
    resp = admin_client.post(f"/api/uploads/{sess['upload_id']}/complete")
    assert resp.status_code == 422 and "Checksum" in resp.json()["detail"]


def test_chunked_upload_validation_still_applies(admin_client):
    """Assembled garbage with an image MIME must be rejected by the SAME
    magic-byte pipeline as direct uploads."""
    r = _mk(admin_client, title="Chunked validation test")
    payload = b"MZ\x90\x00" + b"evil" * 1000
    uid, _ = _chunked_upload(admin_client, r["id"], payload)
    resp = admin_client.post(f"/api/uploads/{uid}/complete")
    assert resp.status_code == 415


def test_upload_session_authz(admin_client):
    r = _mk(admin_client, title="Session authz test")
    payload = PNG + b"A" * 1000
    sess = admin_client.post("/api/uploads", json={
        "report_id": r["id"], "filename": "a.png", "content_type": "image/png",
        "total_size": len(payload)}).json()
    other = _fresh_citizen("uploader")
    # another user cannot touch this session
    assert other.get(f"/api/uploads/{sess['upload_id']}").status_code == 403
    assert other.put(f"/api/uploads/{sess['upload_id']}/chunks/0",
                     content=b"x").status_code == 403


def test_stale_session_cleanup(admin_client):
    from datetime import datetime, timedelta, timezone
    from app.routers.uploads import cleanup_stale_sessions
    r = _mk(admin_client, title="Stale session test")
    sess = admin_client.post("/api/uploads", json={
        "report_id": r["id"], "filename": "s.png", "content_type": "image/png",
        "total_size": 1000}).json()
    db = SessionLocal()
    s = db.get(UploadSession, sess["upload_id"])
    s.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
    db.commit()
    n = cleanup_stale_sessions(db)
    assert n >= 1
    db.refresh(s)
    assert s.status == "aborted"
    db.close()


# ================= offline idempotency =================
def test_client_key_prevents_duplicate_reports(client):
    body = {"title": "Offline idempotency test", "description": "Queued twice from a phone with bad network.",
            "category": "Water", "city": "Addis Ababa", "client_key": "test-offline-key-123",
            "captcha_a": 1, "captcha_b": 1, "captcha_answer": 2}
    r1 = client.post("/api/reports", json=body)
    assert r1.status_code == 201
    r2 = client.post("/api/reports", json=body)     # retry after "reconnect"
    d2 = r2.json()
    assert d2["id"] == r1.json()["id"]
    assert d2.get("deduplicated") is True
    db = SessionLocal()
    assert db.query(Report).filter_by(client_key="test-offline-key-123").count() == 1
    db.close()
