"""Admin management APIs: users, jobs (retry/dead-letter), AI performance,
routing inspection, organization member management."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from ..audit import audit
from ..db import get_db
from ..jobs import retry_job
from ..models import (Job, Organization, OrganizationRule, OrganizationUser,
                      Report, ReportAIAnalysis, Role, Session as SessionModel,
                      User)
from ..security import client_ip, require_admin, require_staff

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ------------------------------ users ------------------------------
@router.get("/users")
def list_users(db: DBSession = Depends(get_db), admin: User = Depends(require_admin),
               q: str | None = None, role: str | None = None,
               page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    qry = db.query(User)
    if q:
        like = f"%{q.lower()}%"
        qry = qry.filter((User.email.ilike(like)) | (User.name.ilike(like)))
    if role:
        qry = qry.filter(User.role == Role(role))
    total = qry.count()
    rows = qry.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    out = []
    for u in rows:
        link = db.query(OrganizationUser).filter(OrganizationUser.user_id == u.id).first()
        out.append({"id": u.id, "name": u.name, "email": u.email, "role": u.role.value,
                    "city": u.city, "is_active": u.is_active,
                    "organization": link.organization.name if link else None,
                    "created_at": u.created_at})
    return {"total": total, "items": out}


class RolePatch(BaseModel):
    role: str


@router.patch("/users/{user_id}/role")
def change_role(user_id: str, body: RolePatch, request: Request,
                admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(422, "You cannot change your own role")
    try:
        new_role = Role(body.role)
    except ValueError:
        raise HTTPException(400, "Unknown role")
    old = u.role.value
    u.role = new_role
    db.commit()
    audit(db, admin.id, "user.role_change", "user", u.id,
          detail=f"{old} -> {new_role.value}", ip=client_ip(request))
    return {"ok": True}


@router.patch("/users/{user_id}/active")
def toggle_active(user_id: str, active: bool, request: Request,
                  admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(422, "You cannot deactivate yourself")
    u.is_active = active
    if not active:  # kill sessions immediately
        db.query(SessionModel).filter(SessionModel.user_id == u.id).delete()
    db.commit()
    audit(db, admin.id, "user.active_toggle", "user", u.id, detail=str(active),
          ip=client_ip(request))
    return {"ok": True}


# ------------------------------ jobs ------------------------------
@router.get("/jobs")
def list_jobs(db: DBSession = Depends(get_db), staff: User = Depends(require_staff),
              status: str | None = None, limit: int = Query(50, le=200)):
    qry = db.query(Job)
    if status:
        qry = qry.filter(Job.status == status)
    rows = qry.order_by(Job.created_at.desc()).limit(limit).all()
    return [{"id": j.id, "name": j.name, "status": j.status, "attempts": j.attempts,
             "max_attempts": j.max_attempts, "last_error": j.last_error,
             "payload": j.payload, "created_at": j.created_at,
             "started_at": j.started_at, "finished_at": j.finished_at} for j in rows]


@router.post("/jobs/{job_id}/retry")
def retry_failed_job(job_id: str, request: Request, admin: User = Depends(require_admin),
                     db: DBSession = Depends(get_db)):
    if not retry_job(job_id):
        raise HTTPException(409, "Job is not in a retryable state (failed/dead)")
    audit(db, admin.id, "job.retry", "job", job_id, ip=client_ip(request))
    return {"ok": True}


# ------------------------------ AI performance ------------------------------
@router.get("/ai-performance")
def ai_performance(db: DBSession = Depends(get_db), staff: User = Depends(require_staff)):
    total = db.query(func.count(ReportAIAnalysis.id)).scalar() or 0
    ok = db.query(func.count(ReportAIAnalysis.id)).filter(ReportAIAnalysis.success == True).scalar() or 0  # noqa: E712
    corrected = db.query(func.count(ReportAIAnalysis.id)) \
                  .filter(ReportAIAnalysis.corrected_by.isnot(None)).scalar() or 0
    avg_conf = db.query(func.avg(ReportAIAnalysis.confidence)).scalar()
    avg_ms = db.query(func.avg(ReportAIAnalysis.duration_ms)).scalar()
    by_model = [{"model": m or "?", "count": c} for m, c in
                db.query(ReportAIAnalysis.model_name, func.count(ReportAIAnalysis.id))
                  .group_by(ReportAIAnalysis.model_name).all()]
    # per-category correction rate (where do humans disagree most?)
    corrections = db.query(ReportAIAnalysis.category, func.count(ReportAIAnalysis.id)) \
        .filter(ReportAIAnalysis.corrected_by.isnot(None)) \
        .group_by(ReportAIAnalysis.category).all()
    return {
        "total_analyses": total, "successful": ok, "failed": total - ok,
        "human_corrected": corrected,
        "correction_rate": round(corrected / total, 3) if total else None,
        "avg_confidence": round(avg_conf, 3) if avg_conf else None,
        "avg_duration_ms": int(avg_ms) if avg_ms else None,
        "by_model": by_model,
        "corrections_by_category": [{"category": c or "?", "count": n} for c, n in corrections],
    }


# ------------------------------ routing inspection ------------------------------
@router.get("/reports/{report_id}/routing")
def routing_explanation(report_id: str, db: DBSession = Depends(get_db),
                        staff: User = Depends(require_staff)):
    """Why was this report routed where it was?"""
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    rule = db.get(OrganizationRule, rpt.routed_rule_id) if rpt.routed_rule_id else None
    org = db.get(Organization, rpt.organization_id) if rpt.organization_id else None
    return {
        "routing_state": rpt.routing_state,
        "organization": org.name if org else None,
        "matched_rule": {
            "id": rule.id, "category": rule.category, "keywords": rule.keywords,
            "city": rule.city, "priority": rule.priority, "auto_assign": rule.auto_assign,
        } if rule else None,
        "ai_recommendation": rpt.ai.responsible_organization if rpt.ai else None,
        "ai_confidence": rpt.ai.confidence if rpt.ai else None,
        "human_confirmed": rpt.human_confirmed,
    }
