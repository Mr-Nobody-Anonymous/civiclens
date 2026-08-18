"""P1: public transparency portal, advanced search + saved searches,
resolution quality metrics. All public output is privacy-preserving:
coarse coordinates, no reporter identity, no private evidence, no internal notes."""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session as DBSession

from ..db import get_db
from ..models import (OPEN_STATUSES, CommunityVote, IssueCluster, Organization,
                      Report, ReportStatus, Subscription, User)
from ..security import get_current_user, require_triage, require_user
from ..serializers import report_public

router = APIRouter(prefix="/api", tags=["transparency"])


# ============================ public transparency portal ============================
@router.get("/transparency")
def transparency(city: str | None = None, db: DBSession = Depends(get_db)):
    """Aggregate civic statistics — no account needed, nothing private exposed."""
    def base(q):
        q = q.filter(Report.is_flagged == False)  # noqa: E712
        return q.filter(Report.city == city) if city else q

    total = base(db.query(func.count(Report.id))).scalar() or 0
    resolved = base(db.query(func.count(Report.id))
                    .filter(Report.status == ReportStatus.resolved)).scalar() or 0
    open_ = base(db.query(func.count(Report.id))
                 .filter(Report.status.in_(OPEN_STATUSES))).scalar() or 0

    top_issues = [{"category": c or "Other", "count": n} for c, n in
                  base(db.query(Report.category, func.count(Report.id)))
                  .group_by(Report.category)
                  .order_by(func.count(Report.id).desc()).limit(8).all()]

    # organization performance (public accountability, aggregate only)
    org_perf = []
    for org in db.query(Organization).filter_by(is_active=True).all():
        q = db.query(func.count(Report.id)).filter(Report.organization_id == org.id,
                                                   Report.is_flagged == False)  # noqa: E712
        if city:
            q = q.filter(Report.city == city)
        t = q.scalar() or 0
        if t == 0:
            continue
        r = q.filter(Report.status == ReportStatus.resolved).scalar() or 0
        # avg resolution days
        rows = db.query(Report.created_at, Report.resolved_at).filter(
            Report.organization_id == org.id, Report.resolved_at.isnot(None)).all()
        days = []
        for c, rr in rows:
            if c and rr:
                if c.tzinfo is None: c = c.replace(tzinfo=timezone.utc)
                if rr.tzinfo is None: rr = rr.replace(tzinfo=timezone.utc)
                days.append((rr - c).total_seconds() / 86400)
        org_perf.append({"organization": org.name, "reports": t, "resolved": r,
                         "resolution_rate": round(r / t, 2),
                         "avg_resolution_days": round(sum(days) / len(days), 1) if days else None})
    org_perf.sort(key=lambda o: -o["reports"])

    # monthly trend, last 6 months
    now = datetime.now(timezone.utc)
    trend = []
    for i in range(5, -1, -1):
        start = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        cnt = base(db.query(func.count(Report.id))
                   .filter(Report.created_at >= start, Report.created_at < end)).scalar() or 0
        res = base(db.query(func.count(Report.id))
                   .filter(Report.resolved_at >= start, Report.resolved_at < end)).scalar() or 0
        trend.append({"month": start.strftime("%Y-%m"), "reports": cnt, "resolved": res})

    active_clusters = db.query(func.count(IssueCluster.id)).filter(
        IssueCluster.status == "open", IssueCluster.report_count > 1,
        *( [IssueCluster.city == city] if city else [] )).scalar() or 0

    return {"city": city or "all", "reports": total, "resolved": resolved, "open": open_,
            "resolution_rate": round(resolved / total, 2) if total else None,
            "top_issues": top_issues, "organization_performance": org_perf,
            "monthly_trend": trend, "active_clusters": active_clusters,
            "privacy_note": ("Aggregated public data. Reporter identities, exact sensitive "
                             "locations and private evidence are never exposed.")}


@router.get("/transparency/clusters/{cluster_id}/timeline")
def public_cluster_timeline(cluster_id: str, db: DBSession = Depends(get_db)):
    """Public issue page data: cluster overview + status timeline of members."""
    c = db.get(IssueCluster, cluster_id)
    if not c:
        raise HTTPException(404, "Cluster not found")
    reports = (db.query(Report).filter(Report.cluster_id == cluster_id,
                                       Report.is_flagged == False)  # noqa: E712
                 .order_by(Report.created_at.asc()).all())
    statuses = {}
    for r in reports:
        statuses[r.status.value] = statuses.get(r.status.value, 0) + 1
    org = None
    for r in reports:
        if r.organization:
            org = r.organization.name
            break
    return {"id": c.id, "title": c.title, "category": c.category, "city": c.city,
            "report_count": c.report_count, "unique_reporters": c.unique_reporters,
            "first_reported": c.first_reported, "last_reported": c.last_reported,
            "status": c.status, "status_breakdown": statuses,
            "organization": org,
            "reports": [report_public(r) for r in reports[:50]]}


# ============================ advanced search ============================
@router.get("/search")
def advanced_search(db: DBSession = Depends(get_db),
                    user: User | None = Depends(get_current_user),
                    q: str | None = None,
                    category: str | None = None,
                    status: str | None = None,
                    min_severity: int | None = Query(None, ge=1, le=5),
                    city: str | None = None,
                    organization: str | None = None,
                    cluster_id: str | None = None,
                    sla: str | None = Query(None, pattern="^(breached)$"),
                    date_from: str | None = None,
                    date_to: str | None = None,
                    lat: float | None = None, lng: float | None = None,
                    radius_m: int = Query(2000, le=20000),
                    page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50)):
    """Deterministic multi-filter search. SLA filter is staff-only."""
    qry = db.query(Report).filter(Report.is_flagged == False)  # noqa: E712
    if q:
        like = f"%{q.lower()}%"
        qry = qry.filter(or_(Report.title.ilike(like), Report.description.ilike(like),
                             Report.public_code.ilike(like), Report.address.ilike(like)))
    if category:
        qry = qry.filter(Report.category == category)
    if status:
        try:
            qry = qry.filter(Report.status == ReportStatus(status))
        except ValueError:
            raise HTTPException(400, "Unknown status")
    if min_severity:
        qry = qry.filter(Report.severity >= min_severity)
    if city:
        qry = qry.filter(Report.city == city)
    if organization:
        qry = (qry.join(Organization, Report.organization_id == Organization.id)
                  .filter(Organization.name.ilike(f"%{organization}%")))
    if cluster_id:
        qry = qry.filter(Report.cluster_id == cluster_id)
    if date_from:
        qry = qry.filter(Report.created_at >= date_from)
    if date_to:
        qry = qry.filter(Report.created_at <= date_to + "T23:59:59")
    if lat is not None and lng is not None:
        deg = radius_m / 111_000
        qry = qry.filter(Report.latitude.between(lat - deg, lat + deg),
                         Report.longitude.between(lng - deg, lng + deg))

    rows_pre = None
    if sla == "breached":
        if not user or user.role.value not in ("admin", "moderator", "org_staff"):
            raise HTTPException(403, "SLA filters are staff-only")
        from ..sla import sla_state
        rows_pre = [r for r in qry.order_by(Report.created_at.desc()).limit(500).all()
                    if sla_state(db, r).get("breached")]

    if rows_pre is not None:
        total = len(rows_pre)
        rows = rows_pre[(page - 1) * page_size: page * page_size]
    else:
        total = qry.count()
        rows = (qry.order_by(Report.created_at.desc())
                   .offset((page - 1) * page_size).limit(page_size).all())
    return {"total": total, "page": page, "items": [report_public(r) for r in rows]}


# ---------------- saved searches (stored as subscriptions with type=search) ----------------
class SavedSearchIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    params: dict


@router.post("/saved-searches", status_code=201)
def save_search(body: SavedSearchIn, user: User = Depends(require_user),
                db: DBSession = Depends(get_db)):
    if len(json.dumps(body.params)) > 2000:
        raise HTTPException(422, "Search too complex")
    existing = db.query(Subscription).filter_by(
        user_id=user.id, target_type="search", target_id=body.label[:64]).first()
    if existing:
        existing.label = json.dumps(body.params)[:120]
        db.commit()
        return {"id": existing.id, "updated": True}
    s = Subscription(user_id=user.id, target_type="search", target_id=body.label[:64],
                     label=json.dumps(body.params)[:120])
    db.add(s)
    db.commit()
    return {"id": s.id}


@router.get("/saved-searches")
def list_saved(user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    rows = db.query(Subscription).filter_by(user_id=user.id, target_type="search").all()
    out = []
    for s in rows:
        try:
            params = json.loads(s.label or "{}")
        except Exception:
            params = {}
        out.append({"id": s.id, "name": s.target_id, "params": params})
    return out


# ============================ resolution quality ============================
@router.get("/organizations/{org_id}/resolution-quality")
def resolution_quality(org_id: str, db: DBSession = Depends(get_db),
                       user: User = Depends(require_triage)):
    """ADVISORY composite per organization: evidence rate, citizen confirmation,
    community agreement, reopen frequency, before/after advisory scores."""
    resolved = db.query(Report).filter(Report.organization_id == org_id,
                                       Report.status.in_([ReportStatus.resolved,
                                                          ReportStatus.reopened])).all()
    if not resolved:
        return {"organization_id": org_id, "sample": 0,
                "advisory": "No resolved reports yet."}
    n = len(resolved)
    with_evidence = sum(1 for r in resolved if any(m.kind == "resolution" for m in r.media))
    confirmed = sum(1 for r in resolved if r.resolution_confirmed is True)
    disputed = sum(1 for r in resolved if r.resolution_confirmed is False)
    reopened = sum(1 for r in resolved if r.status == ReportStatus.reopened)
    adv_scores = [r.resolution_check_score for r in resolved if r.resolution_check_score is not None]
    community_agree = 0
    community_total = 0
    for r in resolved:
        votes = db.query(CommunityVote).filter_by(report_id=r.id).all()
        community_total += len(votes)
        community_agree += sum(1 for v in votes if v.vote == "resolved")

    # composite advisory 0..1 (deterministic, explainable weights)
    quality = (0.30 * (with_evidence / n)
               + 0.25 * (confirmed / n)
               + 0.20 * (1 - reopened / n)
               + 0.15 * (sum(adv_scores) / len(adv_scores) if adv_scores else 0.5)
               + 0.10 * (community_agree / community_total if community_total else 0.5))
    return {
        "organization_id": org_id, "sample": n,
        "evidence_rate": round(with_evidence / n, 2),
        "citizen_confirmed": confirmed, "citizen_disputed": disputed,
        "reopen_rate": round(reopened / n, 2),
        "avg_beforeafter_advisory": round(sum(adv_scores) / len(adv_scores), 2) if adv_scores else None,
        "community_votes": community_total,
        "resolution_quality_advisory": round(quality, 2),
        "advisory_note": ("Composite advisory (evidence 30% · citizen confirmation 25% · "
                          "reopen rate 20% · before/after check 15% · community 10%). "
                          "Advisory only — human judgement decides."),
    }
