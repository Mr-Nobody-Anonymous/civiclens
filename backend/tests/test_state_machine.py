"""State machine + jobs + E2E workflow tests."""
import io
import json

import pytest
from fastapi import HTTPException

from app.db import SessionLocal
from app.models import Job, Report, ReportStatus
from app.state_machine import can_transition, transition


def test_valid_transitions():
    assert can_transition(ReportStatus.submitted, ReportStatus.ai_analysis)
    assert can_transition(ReportStatus.under_review, ReportStatus.assigned)
    assert can_transition(ReportStatus.assigned, ReportStatus.in_progress)
    assert can_transition(ReportStatus.in_progress, ReportStatus.resolved)
    assert can_transition(ReportStatus.resolved, ReportStatus.reopened)
    assert can_transition(ReportStatus.rejected, ReportStatus.reopened)


def test_invalid_transitions():
    assert not can_transition(ReportStatus.submitted, ReportStatus.resolved)
    assert not can_transition(ReportStatus.resolved, ReportStatus.in_progress)
    assert not can_transition(ReportStatus.duplicate, ReportStatus.resolved)
    assert not can_transition(ReportStatus.rejected, ReportStatus.assigned)


def test_transition_service_rejects_invalid(client):
    db = SessionLocal()
    try:
        rpt = Report(title="SM test", description="state machine test description",
                     status=ReportStatus.submitted)
        db.add(rpt)
        db.commit()
        with pytest.raises(HTTPException) as e:
            transition(db, rpt, ReportStatus.resolved)
        assert e.value.status_code == 409
        # forced (system) transitions bypass for pipeline moves
        transition(db, rpt, ReportStatus.under_review, force=True)
        assert rpt.status == ReportStatus.under_review
    finally:
        db.close()


def test_api_rejects_invalid_transition(admin_client):
    r = admin_client.post("/api/reports", json={
        "title": "Invalid transition test", "description": "This is a longer description.",
        "category": "Water", "city": "Addis Ababa"})
    rid = r.json()["id"]
    resp = admin_client.patch(f"/api/reports/{rid}/status", json={"status": "resolved"})
    assert resp.status_code == 409
    resp = admin_client.patch(f"/api/reports/{rid}/status",
                              json={"status": "rejected", "note": "test rejection reason"})
    assert resp.status_code == 200


def test_reject_requires_reason(admin_client):
    r = admin_client.post("/api/reports", json={
        "title": "Reject reason test", "description": "This is a longer description here.",
        "category": "Water", "city": "Addis Ababa"})
    rid = r.json()["id"]
    resp = admin_client.patch(f"/api/reports/{rid}/status", json={"status": "rejected"})
    assert resp.status_code == 422


def test_reopen_by_reporter(citizen_client, admin_client):
    r = citizen_client.post("/api/reports", json={
        "title": "Reopen test report", "description": "The issue that will be resolved and disputed.",
        "category": "Water", "city": "Addis Ababa"})
    rid = r.json()["id"]
    # admin resolves (via valid chain; Water requires evidence -> admin override with note)
    admin_client.patch(f"/api/reports/{rid}/status", json={"status": "under_review"})
    admin_client.patch(f"/api/reports/{rid}/status",
                       json={"status": "resolved", "note": "verified on site (test override)"})
    # citizen reopens/disputes
    resp = citizen_client.post(f"/api/reports/{rid}/reopen?reason=Still broken")
    assert resp.status_code == 200
    assert resp.json()["status"] == "reopened"
    # a stranger cannot reopen
    from tests.conftest import TestClient
    from app.main import app
    stranger = TestClient(app)
    stranger.post("/api/auth/register", json={
        "name": "Stranger", "email": "stranger@test.et", "password": "stranger-pass1"})
    admin_client.patch(f"/api/reports/{rid}/status",
                       json={"status": "resolved", "note": "verified again (test override)"})
    assert stranger.post(f"/api/reports/{rid}/reopen").status_code == 403


# ---------------- jobs ----------------
def test_job_persistence_and_dead_letter(client, monkeypatch):
    from app import jobs as jobs_mod

    calls = {"n": 0}

    def failing_handler(**kw):
        calls["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setitem(jobs_mod.HANDLERS, "always_fails", failing_handler)
    monkeypatch.setattr(jobs_mod.settings, "job_backoff_base_s", 0)

    db = SessionLocal()
    job = Job(name="always_fails", payload=json.dumps({}), max_attempts=2)
    db.add(job)
    db.commit()
    jid = job.id
    db.close()

    jobs_mod.execute_job(jid)   # attempt 1 -> failed (retry scheduled with 0s backoff)
    import time
    time.sleep(0.3)             # allow the timer-thread retry (attempt 2) to run

    db = SessionLocal()
    j = db.get(Job, jid)
    assert j.status == "dead"
    assert "boom" in j.last_error
    assert j.attempts == 2
    db.close()
    assert calls["n"] == 2


def test_job_idempotent_execution(client, monkeypatch):
    from app import jobs as jobs_mod
    calls = {"n": 0}
    monkeypatch.setitem(jobs_mod.HANDLERS, "count_me", lambda **kw: calls.__setitem__("n", calls["n"] + 1))
    db = SessionLocal()
    job = Job(name="count_me", payload="{}")
    db.add(job)
    db.commit()
    jid = job.id
    db.close()
    jobs_mod.execute_job(jid)
    jobs_mod.execute_job(jid)  # second run: job already done -> no-op
    assert calls["n"] == 1


def test_process_report_idempotent_no_duplicate_analysis(client, monkeypatch):
    """finalize twice must not create two analyses or two notification sets.
    AI is forced offline here to exercise the failure path deterministically."""
    from app import jobs as jobs_mod
    monkeypatch.setattr(jobs_mod.settings, "ai_service_url", "http://127.0.0.1:1")
    r = client.post("/api/reports", json={
        "title": "Pothole near the school gate", "description":
        "Deep pothole endangering children walking to school every morning.",
        "category": "Roads & Transportation", "city": "Addis Ababa",
        "captcha_a": 1, "captcha_b": 2, "captcha_answer": 3})
    rid = r.json()["id"]
    from app.jobs import process_report
    process_report(rid)   # direct call (AI service offline in tests -> failure path)
    process_report(rid)   # second call must be a no-op
    db = SessionLocal()
    from app.models import ReportAIAnalysis
    n = db.query(ReportAIAnalysis).filter_by(report_id=rid).count()
    rpt = db.get(Report, rid)
    assert n == 1
    # AI offline in tests -> report is safely parked for manual review, not lost
    assert rpt.status == ReportStatus.under_review
    assert rpt.routing_state == "needs_manual_routing"
    db.close()


def test_media_upload_rejects_corrupt_video(client):
    r = client.post("/api/reports", json={
        "title": "Corrupt video test", "description": "Testing corrupt video rejection.",
        "category": "Water", "city": "Addis Ababa",
        "captcha_a": 1, "captcha_b": 2, "captcha_answer": 3})
    rid = r.json()["id"]
    # correct magic bytes but not a real decodable video
    fake = io.BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 500)
    resp = client.post(f"/api/reports/{rid}/media",
                       files={"file": ("clip.mp4", fake, "video/mp4")})
    assert resp.status_code == 422


def test_attachment_limit(client):
    r = client.post("/api/reports", json={
        "title": "Attachment limit test", "description": "Testing the attachments cap here.",
        "category": "Water", "city": "Addis Ababa",
        "captcha_a": 1, "captcha_b": 2, "captcha_answer": 3})
    rid = r.json()["id"]
    ok = 0
    for i in range(8):
        png = io.BytesIO(b"\x89PNG\r\n\x1a\n" + bytes([i]) * 100)
        resp = client.post(f"/api/reports/{rid}/media",
                           files={"file": (f"p{i}.png", png, "image/png")})
        if resp.status_code == 201:
            ok += 1
        else:
            assert resp.status_code == 413
    assert ok == 6  # CL_MAX_ATTACHMENTS default
