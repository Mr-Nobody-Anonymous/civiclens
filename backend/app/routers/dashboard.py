from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from ..db import get_db
from ..models import (OPEN_STATUSES, AuditLog, Notification, Organization,
                      OrganizationUser, Report, ReportAIAnalysis, ReportStatus,
                      Role, User)
from ..security import require_staff, require_user
from ..serializers import report_privileged

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/public-stats")
def public_stats(db: DBSession = Depends(get_db)):
    """Landing page counters — safe for anonymous access."""
    total = db.query(func.count(Report.id)).scalar() or 0
    resolved = db.query(func.count(Report.id)).filter(Report.status == ReportStatus.resolved).scalar() or 0
    orgs = db.query(func.count(Organization.id)).filter(Organization.is_active == True).scalar() or 0  # noqa: E712
    routed = db.query(func.count(Report.id)).filter(Report.organization_id.isnot(None)).scalar() or 0
    return {"reports": total, "resolved": resolved, "organizations": orgs, "routed": routed}


@router.get("/stats")
def admin_stats(db: DBSession = Depends(get_db), user: User = Depends(require_staff)):
    now = datetime.now(timezone.utc)
    def count(*flt):
        return db.query(func.count(Report.id)).filter(*flt).scalar() or 0

    total = count()
    today = count(Report.created_at >= now - timedelta(days=1))
    week = count(Report.created_at >= now - timedelta(days=7))
    month = count(Report.created_at >= now - timedelta(days=30))
    open_ = count(Report.status.in_(OPEN_STATUSES))
    resolved = count(Report.status == ReportStatus.resolved)
    flagged = count(Report.is_flagged == True)  # noqa: E712

    by_cat = dict(db.query(Report.category, func.count(Report.id))
                  .filter(Report.category.isnot(None)).group_by(Report.category).all())
    by_status = {s.value: 0 for s in ReportStatus}
    for s, c in db.query(Report.status, func.count(Report.id)).group_by(Report.status).all():
        by_status[s.value] = c
    by_sev = {i: 0 for i in range(1, 6)}
    for s, c in db.query(Report.severity, func.count(Report.id)) \
                  .filter(Report.severity.isnot(None)).group_by(Report.severity).all():
        by_sev[int(s)] = c
    by_org = [{"name": n, "count": c} for n, c in
              db.query(Organization.name, func.count(Report.id))
                .join(Report, Report.organization_id == Organization.id)
                .group_by(Organization.name).order_by(func.count(Report.id).desc()).all()]

    avg_conf = db.query(func.avg(ReportAIAnalysis.confidence)).scalar()
    corrected = db.query(func.count(ReportAIAnalysis.id)) \
                  .filter(ReportAIAnalysis.corrected_by.isnot(None)).scalar() or 0
    analyzed = db.query(func.count(ReportAIAnalysis.id)).scalar() or 0

    # avg resolution time (hours)
    res_rows = db.query(Report.created_at, Report.resolved_at) \
                 .filter(Report.resolved_at.isnot(None)).all()
    if res_rows:
        deltas = []
        for c, r in res_rows:
            if c and r:
                if c.tzinfo is None:
                    c = c.replace(tzinfo=timezone.utc)
                if r.tzinfo is None:
                    r = r.replace(tzinfo=timezone.utc)
                deltas.append((r - c).total_seconds() / 3600)
        avg_res_h = round(sum(deltas) / len(deltas), 1) if deltas else None
    else:
        avg_res_h = None

    # hotspots: coarse geographic grid
    hot = {}
    for lat, lng in db.query(Report.latitude, Report.longitude) \
                      .filter(Report.latitude.isnot(None)).all():
        key = (round(lat, 2), round(lng, 2))
        hot[key] = hot.get(key, 0) + 1
    hotspots = [{"lat": k[0], "lng": k[1], "count": v}
                for k, v in sorted(hot.items(), key=lambda x: -x[1])[:12]]

    # 14-day trend
    trend = []
    for i in range(13, -1, -1):
        d0 = (now - timedelta(days=i)).date()
        c = count(func.date(Report.created_at) == d0.isoformat())
        trend.append({"date": d0.isoformat(), "count": c})

    return {
        "total": total, "today": today, "week": week, "month": month,
        "open": open_, "resolved": resolved, "flagged": flagged,
        "by_category": by_cat, "by_status": by_status, "by_severity": by_sev,
        "by_organization": by_org,
        "ai": {"avg_confidence": round(avg_conf, 3) if avg_conf else None,
               "analyzed": analyzed, "corrected": corrected},
        "avg_resolution_hours": avg_res_h, "hotspots": hotspots, "trend": trend,
    }


@router.get("/org-stats")
def org_stats(db: DBSession = Depends(get_db), user: User = Depends(require_user)):
    if user.role not in (Role.org_staff, Role.admin):
        raise HTTPException(403, "Organization staff only")
    link = db.query(OrganizationUser).filter(OrganizationUser.user_id == user.id).first()
    if not link and user.role != Role.admin:
        raise HTTPException(403, "No organization membership")
    org_id = link.organization_id if link else None
    if not org_id:
        raise HTTPException(400, "Admin: use /api/dashboard/stats instead")

    def count(*flt):
        return db.query(func.count(Report.id)).filter(Report.organization_id == org_id, *flt).scalar() or 0

    by_status = {}
    for s, c in db.query(Report.status, func.count(Report.id)) \
                  .filter(Report.organization_id == org_id).group_by(Report.status).all():
        by_status[s.value] = c
    by_sev = {}
    for s, c in db.query(Report.severity, func.count(Report.id)) \
                  .filter(Report.organization_id == org_id, Report.severity.isnot(None)) \
                  .group_by(Report.severity).all():
        by_sev[int(s)] = c
    org = db.get(Organization, org_id)
    return {"organization": org.name if org else "?",
            "total": count(), "open": count(Report.status.in_(OPEN_STATUSES)),
            "resolved": count(Report.status == ReportStatus.resolved),
            "by_status": by_status, "by_severity": by_sev}


@router.get("/org-reports")
def org_reports(db: DBSession = Depends(get_db), user: User = Depends(require_user),
                status: str | None = None):
    """Reports visible ONLY to the user's own organization."""
    if user.role != Role.org_staff and user.role != Role.admin:
        raise HTTPException(403, "Organization staff only")
    link = db.query(OrganizationUser).filter(OrganizationUser.user_id == user.id).first()
    if not link:
        raise HTTPException(403, "No organization membership")
    q = db.query(Report).filter(Report.organization_id == link.organization_id)
    if status:
        q = q.filter(Report.status == ReportStatus(status))
    rows = q.order_by(Report.severity.desc().nullslast(), Report.created_at.desc()).limit(200).all()
    return [report_privileged(r) for r in rows]


# ---------------- notifications + audit ----------------
misc_router = APIRouter(prefix="/api", tags=["misc"])


@misc_router.get("/notifications")
def my_notifications(db: DBSession = Depends(get_db), user: User = Depends(require_user)):
    rows = (db.query(Notification).filter(Notification.user_id == user.id)
              .order_by(Notification.created_at.desc()).limit(50).all())
    return [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body,
             "report_id": n.report_id, "read": n.read, "created_at": n.created_at}
            for n in rows]


@misc_router.post("/notifications/read-all")
def read_all(db: DBSession = Depends(get_db), user: User = Depends(require_user)):
    db.query(Notification).filter(Notification.user_id == user.id).update({"read": True})
    db.commit()
    return {"ok": True}


@misc_router.get("/audit-logs")
def audit_logs(db: DBSession = Depends(get_db), user: User = Depends(require_staff),
               limit: int = 100):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).all()
    return [{"id": a.id, "user_id": a.user_id, "action": a.action, "entity": a.entity,
             "entity_id": a.entity_id, "detail": a.detail, "ip": a.ip,
             "created_at": a.created_at} for a in rows]


@misc_router.get("/meta")
def meta(db: DBSession = Depends(get_db)):
    from ..config import settings
    from ..models import CATEGORIES
    return {"categories": CATEGORIES,
            "cities": settings.cities.split(","),
            "default_center": {"lat": settings.default_city_lat, "lng": settings.default_city_lng},
            "statuses": [s.value for s in ReportStatus],
            "max_video_mb": settings.max_video_mb, "max_image_mb": settings.max_image_mb}
