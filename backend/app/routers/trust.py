"""CivicLens 2.0 trust & operations APIs:
AI review queue · issue clusters · SLA status · real-time SSE stream."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from ..audit import audit
from ..db import get_db
from ..models import (AIReview, EscalationEvent, IssueCluster, Report, User)
from ..review import decide
from ..security import client_ip, get_current_user, require_staff, require_triage, require_user
from ..serializers import ai_out, report_privileged
from ..sla import check_slas, org_sla_stats, sla_state

router = APIRouter(prefix="/api", tags=["trust-ops"])


# ---------------------- AI review queue ----------------------
@router.get("/reviews")
def review_queue(db: DBSession = Depends(get_db), staff: User = Depends(require_staff),
                 status: str = "pending", reason: str | None = None,
                 limit: int = Query(50, le=200)):
    q = db.query(AIReview).filter(AIReview.status == status)
    if reason:
        q = q.filter(AIReview.reason == reason)
    rows = q.order_by(AIReview.created_at.asc()).limit(limit).all()
    counts = dict(db.query(AIReview.reason, func.count(AIReview.id))
                    .filter(AIReview.status == "pending").group_by(AIReview.reason).all())
    return {
        "counts": {"total": sum(counts.values()), **counts},
        "items": [{
            "id": rv.id, "reason": rv.reason, "detail": rv.detail,
            "created_at": rv.created_at,
            "report": report_privileged(rv.report) if rv.report else None,
            "ai": ai_out(rv.analysis) if rv.analysis else None,
        } for rv in rows],
    }


class ReviewDecision(BaseModel):
    action: str = Field(pattern="^(accepted|corrected|rejected)$")
    corrected_category: str | None = None
    corrected_severity: int | None = Field(default=None, ge=1, le=5)
    reason: str = ""


@router.post("/reviews/{review_id}/decide")
def decide_review(review_id: str, body: ReviewDecision, request: Request,
                  staff: User = Depends(require_staff), db: DBSession = Depends(get_db)):
    rv = db.get(AIReview, review_id)
    if not rv:
        raise HTTPException(404, "Review not found")
    if rv.status != "pending":
        raise HTTPException(409, "Review already decided")
    if body.action == "corrected" and not (body.corrected_category or body.corrected_severity):
        raise HTTPException(422, "Correction requires a category and/or severity")
    decide(db, rv, staff.id, body.action,
           body.corrected_category, body.corrected_severity, body.reason)
    audit(db, staff.id, "ai_review.decide", "ai_review", rv.id,
          detail=f"{body.action} {body.corrected_category or ''} {body.corrected_severity or ''}",
          ip=client_ip(request))
    return {"ok": True, "status": rv.status}


@router.get("/reviews/history")
def review_history(db: DBSession = Depends(get_db), staff: User = Depends(require_staff),
                   limit: int = Query(50, le=200)):
    """AI prediction -> human decision dataset (for model evaluation)."""
    rows = (db.query(AIReview).filter(AIReview.status != "pending")
              .order_by(AIReview.decided_at.desc()).limit(limit).all())
    return [{
        "id": rv.id, "reason": rv.reason, "status": rv.status,
        "ai_category": rv.analysis.category if rv.analysis else None,
        "ai_severity": rv.analysis.severity if rv.analysis else None,
        "ai_confidence": rv.analysis.confidence if rv.analysis else None,
        "corrected_category": rv.corrected_category,
        "corrected_severity": rv.corrected_severity,
        "decision_reason": rv.decision_reason,
        "reviewer": rv.reviewer.name if rv.reviewer else None,
        "decided_at": rv.decided_at,
    } for rv in rows]


# ---------------------- issue clusters ----------------------
@router.get("/clusters")
def list_clusters(db: DBSession = Depends(get_db),
                  status: str = "open", city: str | None = None,
                  limit: int = Query(50, le=200)):
    q = db.query(IssueCluster).filter(IssueCluster.status == status)
    if city:
        q = q.filter(IssueCluster.city == city)
    rows = (q.filter(IssueCluster.report_count > 1)
              .order_by(IssueCluster.report_count.desc()).limit(limit).all())
    return [{
        "id": c.id, "title": c.title, "category": c.category, "city": c.city,
        "latitude": round(c.latitude, 4) if c.latitude else None,
        "longitude": round(c.longitude, 4) if c.longitude else None,
        "severity": c.severity, "report_count": c.report_count,
        "unique_reporters": c.unique_reporters,
        "first_reported": c.first_reported, "last_reported": c.last_reported,
    } for c in rows]


@router.get("/clusters/{cluster_id}")
def cluster_detail(cluster_id: str, db: DBSession = Depends(get_db),
                   user: User | None = Depends(get_current_user)):
    c = db.get(IssueCluster, cluster_id)
    if not c:
        raise HTTPException(404, "Cluster not found")
    reports = (db.query(Report).filter(Report.cluster_id == cluster_id,
                                       Report.is_flagged == False)  # noqa: E712
                 .order_by(Report.created_at.desc()).limit(100).all())
    from ..serializers import report_public
    return {
        "id": c.id, "title": c.title, "category": c.category, "city": c.city,
        "severity": c.severity, "report_count": c.report_count,
        "unique_reporters": c.unique_reporters, "status": c.status,
        "first_reported": c.first_reported, "last_reported": c.last_reported,
        "reports": [report_public(r) for r in reports],
    }


# ---------------------- SLA ----------------------
@router.get("/reports/{report_id}/sla")
def report_sla(report_id: str, db: DBSession = Depends(get_db),
               user: User = Depends(require_triage)):
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    return sla_state(db, r)


@router.get("/sla/escalations")
def escalations(db: DBSession = Depends(get_db), staff: User = Depends(require_staff),
                limit: int = Query(50, le=200)):
    rows = (db.query(EscalationEvent)
              .order_by(EscalationEvent.created_at.desc()).limit(limit).all())
    out = []
    for e in rows:
        r = db.get(Report, e.report_id)
        out.append({"id": e.id, "kind": e.kind, "overdue_hours": e.overdue_hours,
                    "created_at": e.created_at,
                    "report_code": r.public_code if r else None,
                    "report_id": e.report_id,
                    "report_title": r.title if r else None,
                    "organization": r.organization.name if r and r.organization else None})
    return out


@router.post("/sla/check")
def run_sla_check(db: DBSession = Depends(get_db), staff: User = Depends(require_staff)):
    """On-demand sweep (also runs automatically in the worker every 5 min)."""
    return {"escalations_created": check_slas(db)}


@router.get("/organizations/{org_id}/sla-stats")
def org_sla(org_id: str, db: DBSession = Depends(get_db),
            user: User = Depends(require_triage)):
    return org_sla_stats(db, org_id)


# ---------------------- real-time stream (SSE) ----------------------
@router.get("/stream")
async def stream(user: User = Depends(require_user)):
    """Server-Sent Events: pushes this user's notifications in real time.
    Falls back transparently — clients keep polling if SSE drops."""
    from ..events import subscribe
    return StreamingResponse(
        subscribe(user.id), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
