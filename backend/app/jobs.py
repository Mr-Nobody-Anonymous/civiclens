"""Background job system with persistent state, retries and dead-letter.

Every job gets a row in the `jobs` table (queued|running|done|failed|dead).
Execution backend is either an in-process thread pool (dev) or Redis + worker
processes (prod). A crashed worker never loses work: the job row stays
`queued`/`failed` and can be retried from the admin dashboard.

process_report is idempotent: if an AI analysis already exists it will not be
re-created and no duplicate notifications are sent.
"""
import base64
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx

from .config import settings
from .db import SessionLocal
from . import media as mediaproc
from .models import (Job, Report, ReportAIAnalysis, ReportAssignment,
                     ReportStatus, ReportStatusHistory, User)
from .notify import notify
from .routing import route_report
from .state_machine import transition
from .storage import storage

log = logging.getLogger("civiclens.jobs")
_executor = ThreadPoolExecutor(max_workers=2)


def enqueue(job_name: str, **kwargs) -> str:
    """Create a persistent job row and dispatch it."""
    db = SessionLocal()
    try:
        job = Job(name=job_name, payload=json.dumps(kwargs),
                  max_attempts=settings.job_max_attempts)
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    if settings.job_backend == "redis":
        import redis
        r = redis.from_url(settings.redis_url)
        r.rpush("civiclens:jobs", json.dumps({"job_id": job_id}))
    else:
        _executor.submit(execute_job, job_id)
    return job_id


def retry_job(job_id: str) -> bool:
    """Admin-triggered retry of a failed/dead job."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job or job.status not in ("failed", "dead"):
            return False
        job.status = "queued"
        job.last_error = None
        db.commit()
    finally:
        db.close()
    if settings.job_backend == "redis":
        import redis
        redis.from_url(settings.redis_url).rpush("civiclens:jobs", json.dumps({"job_id": job_id}))
    else:
        _executor.submit(execute_job, job_id)
    return True


def execute_job(job_id: str):
    """Run one job with attempt tracking + exponential backoff scheduling."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job or job.status in ("done", "running"):
            return  # idempotency: don't double-run
        job.status = "running"
        job.attempts = (job.attempts or 0) + 1
        job.started_at = datetime.now(timezone.utc)
        db.commit()
        name, kwargs = job.name, json.loads(job.payload or "{}")
    finally:
        db.close()

    try:
        HANDLERS[name](**kwargs)
        _finish(job_id, "done")
    except Exception as e:
        log.exception("job %s (%s) failed", job_id, name)
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job.attempts >= job.max_attempts:
                job.status = "dead"
                job.last_error = f"{type(e).__name__}: {e}"[:2000]
                db.commit()
                _mark_report_failed(kwargs, job.last_error)
            else:
                job.status = "failed"
                job.last_error = f"{type(e).__name__}: {e}"[:2000]
                backoff = settings.job_backoff_base_s * (2 ** (job.attempts - 1))
                job.run_after = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                db.commit()
                # auto-retry with backoff (thread backend); redis worker polls run_after
                if settings.job_backend != "redis":
                    import threading
                    threading.Timer(backoff, execute_job, args=[job_id]).start()
                else:
                    import redis
                    redis.from_url(settings.redis_url).rpush(
                        "civiclens:jobs:delayed",
                        json.dumps({"job_id": job_id, "run_after": job.run_after.isoformat()}))
        finally:
            db.close()


def _finish(job_id: str, status: str):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            job.status = status
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def _mark_report_failed(kwargs: dict, error: str):
    """Dead-lettered analysis: report goes to manual review, never disappears."""
    rid = kwargs.get("report_id")
    if not rid:
        return
    db = SessionLocal()
    try:
        rpt = db.get(Report, rid)
        if rpt:
            rpt.processing_state = "failed"
            rpt.processing_error = error[:1000]
            if rpt.status in (ReportStatus.submitted, ReportStatus.ai_analysis):
                transition(db, rpt, ReportStatus.under_review, note=
                           "Automatic analysis failed — manual review required", force=True)
            db.commit()
    finally:
        db.close()


def _b64_file(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def process_report(report_id: str):
    """Async pipeline: frames -> local AI -> confidence gate -> routing -> notify.

    Idempotent: skips AI + notifications if analysis already exists.
    Never overwrites human-confirmed classifications.
    """
    db = SessionLocal()
    try:
        report = db.get(Report, report_id)
        if not report:
            return
        if report.ai is not None:
            log.info("report %s already analyzed; skipping (idempotent)", report_id)
            return

        report.processing_state = "processing"
        db.commit()
        if report.status == ReportStatus.submitted:
            transition(db, report, ReportStatus.ai_analysis,
                       note="Automatic AI analysis started", force=True)

        # ---- collect visual evidence ----
        frames_b64, images_b64, video_meta = [], [], None
        for m in report.media:
            try:
                local_path = storage.path(m.storage_key)
                if m.kind == "video":
                    video_meta = mediaproc.probe(local_path)
                    for fp in mediaproc.extract_frames(local_path, settings.ai_frames_per_video):
                        frames_b64.append(_b64_file(fp))
                        os.remove(fp)
                elif m.kind == "image":
                    images_b64.append(_b64_file(local_path))
            except Exception:
                log.exception("media prep failed for %s (continuing without it)", m.id)

        # ---- call local AI service ----
        payload = {
            "title": report.title, "description": report.description,
            "comments": report.comments or "", "user_category": report.user_category,
            "city": report.city, "address": report.address,
            "frames_b64": frames_b64, "images_b64": images_b64, "video_meta": video_meta,
        }
        started = datetime.now(timezone.utc)
        ai = None
        ai_error = None
        try:
            r = httpx.post(f"{settings.ai_service_url}/analyze", json=payload, timeout=300)
            r.raise_for_status()
            ai = r.json()
            # validate the AI contract — unknown categories/invalid severity are rejected
            from .models import CATEGORIES
            if ai.get("category") not in CATEGORIES:
                raise ValueError(f"AI returned unknown category: {ai.get('category')!r}")
            ai["severity"] = max(1, min(5, int(ai.get("severity", 3))))
            ai["confidence"] = max(0.0, min(1.0, float(ai.get("confidence", 0.5))))
        except Exception as e:
            ai = None
            ai_error = f"{type(e).__name__}: {e}"[:500]
            log.warning("AI analysis unavailable (%s); manual review", ai_error)
        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

        input_kind = "text"
        if frames_b64:
            input_kind += "+frames"
        if images_b64:
            input_kind += "+images"

        if ai:
            db.add(ReportAIAnalysis(
                report_id=report.id, category=ai["category"], issue_type=ai["issue_type"],
                severity=ai["severity"], confidence=ai["confidence"], urgency=ai["urgency"],
                responsible_organization=ai["responsible_organization"],
                organization_type=ai["organization_type"], reasoning=ai["reasoning"],
                model_name=settings.ai_model_name or ai["model_name"],
                model_version=ai["model_version"],
                analyzer=ai.get("model_name", "unknown").split(":")[0],
                input_kind=input_kind, duration_ms=duration_ms, success=True,
                frames_analyzed=ai.get("frames_analyzed", 0), raw_json=json.dumps(ai)))

            # Never overwrite a human-confirmed classification
            if not report.human_confirmed:
                report.category = ai["category"]
                report.issue_type = ai["issue_type"]
                report.severity = ai["severity"]

            # ---- routing rules ----
            org, rule = route_report(db, report, ai["category"],
                                     f"{report.title} {report.description}")
            if org:
                report.organization_id = org.id
                report.routing_state = "routed"
                report.routed_rule_id = rule.id if rule else None
                db.add(ReportAssignment(report_id=report.id, organization_id=org.id,
                                        source="rule" if rule else "ai",
                                        note=f"Routed by rule (category: {ai['category']})"))
                # Confidence gate: auto-assign requires rule.auto_assign AND high confidence
                if rule and rule.auto_assign and ai["confidence"] >= settings.ai_conf_high:
                    transition(db, report, ReportStatus.assigned, force=True,
                               note=f"Auto-assigned to {org.name} (rule + confidence "
                                    f"{int(ai['confidence']*100)}%)")
                else:
                    why = ("low AI confidence — manual classification required"
                           if ai["confidence"] < settings.ai_conf_low else
                           "awaiting human confirmation")
                    transition(db, report, ReportStatus.under_review, force=True,
                               note=f"AI recommends {org.name}; {why}")
            else:
                report.routing_state = "needs_manual_routing"
                transition(db, report, ReportStatus.under_review, force=True,
                           note="No routing rule matched — needs manual routing")
        else:
            db.add(ReportAIAnalysis(
                report_id=report.id, success=False, reasoning=f"Analysis failed: {ai_error}",
                model_name="unavailable", model_version="-", analyzer="none",
                input_kind=input_kind, duration_ms=duration_ms))
            report.routing_state = "needs_manual_routing"
            transition(db, report, ReportStatus.under_review, force=True,
                       note="AI unavailable — manual review required")

        report.processing_state = "done" if ai else "failed"
        report.processing_error = ai_error
        db.commit()

        # ---- notify reporter (exactly once — guarded by the ai-exists check above) ----
        if report.reporter_id:
            reporter = db.get(User, report.reporter_id)
            am = reporter and reporter.language == "am"
            if ai:
                title = (f"የ AI ትንተና ተጠናቋል ({report.public_code})" if am
                         else f"AI analysis complete for {report.public_code}")
                body = (f"ሪፖርትዎ እንደ {ai['category']} / {ai['issue_type']} ተመድቧል "
                        f"(ክብደት {ai['severity']}/5)። የሰው ገምጋሚ ይህን ሊያስተካክል ይችላል።" if am else
                        f"Your report was classified as {ai['category']} / {ai['issue_type']} "
                        f"(severity {ai['severity']}/5, confidence {int(ai['confidence']*100)}%). "
                        "A human reviewer may adjust this classification.")
                notify(db, reporter, "analyzed", title, body, report_id=report.id)
    finally:
        db.close()


def retry_analysis(report_id: str):
    """Authorized re-run of AI analysis: clears previous result first (explicit request)."""
    db = SessionLocal()
    try:
        rpt = db.get(Report, report_id)
        if rpt and rpt.ai:
            db.delete(rpt.ai)
            rpt.processing_state = "queued"
            db.commit()
    finally:
        db.close()
    process_report(report_id)


HANDLERS = {
    "process_report": process_report,
    "retry_analysis": retry_analysis,
}


def run_job(job_name: str, kwargs: dict):
    """Legacy direct-execution entrypoint (kept for tests)."""
    HANDLERS[job_name](**kwargs)
