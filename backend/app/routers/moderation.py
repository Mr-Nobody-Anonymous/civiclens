"""Unified moderation center.

One queue combining every human-attention signal:
  ai_review        pending AIReview entries (low conf / severity / disagreement /
                   integrity / resolution_check)
  flagged_report   reports flagged by users or staff
  flagged_comment  comments reported as abusive
  dup_cluster      clusters with unusually many reports (possible brigading OR
                   genuinely urgent issue — human judgement either way)

Principles: no destructive automatic actions; hide/unhide is reversible; every
action is audited; bulk actions limited to safe, reversible operations.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from ..audit import audit
from ..db import get_db
from ..models import (AIReview, IssueCluster, Report, ReportComment, User)
from ..security import client_ip, require_staff, require_user
from ..serializers import report_privileged

router = APIRouter(prefix="/api/moderation", tags=["moderation"])

DUP_CLUSTER_THRESHOLD = 5   # clusters with >= N reports surface for a human look


@router.get("/queue")
def unified_queue(db: DBSession = Depends(get_db), staff: User = Depends(require_staff),
                  kind: str | None = None, limit: int = Query(50, le=200)):
    items = []

    if kind in (None, "ai_review"):
        for rv in (db.query(AIReview).filter(AIReview.status == "pending")
                     .order_by(AIReview.created_at.asc()).limit(limit).all()):
            items.append({
                "kind": "ai_review", "id": rv.id, "reason": rv.reason,
                "detail": rv.detail, "created_at": rv.created_at,
                "severity": rv.report.severity if rv.report else None,
                "report": report_privileged(rv.report) if rv.report else None})

    if kind in (None, "flagged_report"):
        for r in (db.query(Report).filter(Report.is_flagged == True)  # noqa: E712
                    .order_by(Report.created_at.desc()).limit(limit).all()):
            items.append({
                "kind": "flagged_report", "id": r.id, "reason": "flagged",
                "detail": r.flag_reason, "created_at": r.created_at,
                "severity": r.severity, "report": report_privileged(r)})

    if kind in (None, "flagged_comment"):
        for c in (db.query(ReportComment)
                    .filter(ReportComment.is_flagged == True,        # noqa: E712
                            ReportComment.hidden == False)           # noqa: E712
                    .order_by(ReportComment.created_at.desc()).limit(limit).all()):
            items.append({
                "kind": "flagged_comment", "id": c.id, "reason": "reported_comment",
                "detail": c.body[:300], "created_at": c.created_at,
                "severity": None, "report_id": c.report_id,
                "author": c.user.name if c.user else "Anonymous"})

    if kind in (None, "dup_cluster"):
        for cl in (db.query(IssueCluster)
                     .filter(IssueCluster.status == "open",
                             IssueCluster.report_count >= DUP_CLUSTER_THRESHOLD)
                     .order_by(IssueCluster.report_count.desc()).limit(limit).all()):
            items.append({
                "kind": "dup_cluster", "id": cl.id, "reason": "high_volume_cluster",
                "detail": f"{cl.report_count} reports from {cl.unique_reporters} "
                          f"reporter(s): {cl.title[:120]}",
                "created_at": cl.last_reported, "severity": cl.severity})

    # severity-first ordering, then oldest first (don't starve old items)
    items.sort(key=lambda x: (-(x.get("severity") or 0),
                              x["created_at"].isoformat() if x["created_at"] else ""))
    counts = {
        "ai_review": db.query(func.count(AIReview.id)).filter(AIReview.status == "pending").scalar() or 0,
        "flagged_report": db.query(func.count(Report.id)).filter(Report.is_flagged == True).scalar() or 0,  # noqa: E712
        "flagged_comment": db.query(func.count(ReportComment.id))
            .filter(ReportComment.is_flagged == True, ReportComment.hidden == False).scalar() or 0,  # noqa: E712
        "dup_cluster": db.query(func.count(IssueCluster.id))
            .filter(IssueCluster.status == "open",
                    IssueCluster.report_count >= DUP_CLUSTER_THRESHOLD).scalar() or 0,
    }
    counts["total"] = sum(counts.values())
    return {"counts": counts, "items": items[:limit]}


# ---------------- comments: report / hide / restore (reversible) ----------------
@router.post("/comments/{comment_id}/flag")
def flag_comment(comment_id: str, request: Request, user: User = Depends(require_user),
                 db: DBSession = Depends(get_db)):
    c = db.get(ReportComment, comment_id)
    if not c:
        raise HTTPException(404, "Comment not found")
    c.is_flagged = True
    db.commit()
    audit(db, user.id, "comment.flag", "comment", c.id, ip=client_ip(request))
    return {"ok": True}


class HideBody(BaseModel):
    hidden: bool
    reason: str = ""


@router.post("/comments/{comment_id}/hide")
def hide_comment(comment_id: str, body: HideBody, request: Request,
                 staff: User = Depends(require_staff), db: DBSession = Depends(get_db)):
    c = db.get(ReportComment, comment_id)
    if not c:
        raise HTTPException(404, "Comment not found")
    c.hidden = body.hidden
    if not body.hidden:
        c.is_flagged = False   # restore clears the flag
    db.commit()
    audit(db, staff.id, "comment.hide" if body.hidden else "comment.restore",
          "comment", c.id, detail=body.reason, ip=client_ip(request))
    return {"ok": True}


# ---------------- safe bulk actions ----------------
class BulkBody(BaseModel):
    ids: list[str]
    action: str          # unflag_reports | hide_comments | restore_comments
    reason: str = ""


@router.post("/bulk")
def bulk(body: BulkBody, request: Request, staff: User = Depends(require_staff),
         db: DBSession = Depends(get_db)):
    if body.action not in ("unflag_reports", "hide_comments", "restore_comments"):
        raise HTTPException(422, "Unknown or unsafe bulk action")
    if len(body.ids) > 50:
        raise HTTPException(422, "Bulk actions limited to 50 items")
    done = 0
    for _id in body.ids:
        if body.action == "unflag_reports":
            r = db.get(Report, _id)
            if r and r.is_flagged:
                r.is_flagged = False
                r.flag_reason = None
                done += 1
        else:
            c = db.get(ReportComment, _id)
            if c:
                c.hidden = body.action == "hide_comments"
                if body.action == "restore_comments":
                    c.is_flagged = False
                done += 1
    db.commit()
    audit(db, staff.id, f"moderation.bulk.{body.action}", "bulk", "",
          detail=f"{done} items: {body.reason}", ip=client_ip(request))
    return {"ok": True, "processed": done}


@router.get("/history")
def moderation_history(db: DBSession = Depends(get_db), staff: User = Depends(require_staff),
                       limit: int = Query(100, le=300)):
    from ..models import AuditLog
    rows = (db.query(AuditLog)
              .filter(AuditLog.action.in_([
                  "comment.flag", "comment.hide", "comment.restore",
                  "report.flag", "report.unflag", "ai_review.decide",
                  "moderation.bulk.unflag_reports", "moderation.bulk.hide_comments",
                  "moderation.bulk.restore_comments",
                  "report.resolve_no_evidence_override"]))
              .order_by(AuditLog.created_at.desc()).limit(limit).all())
    return [{"id": a.id, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
             "detail": a.detail, "user_id": a.user_id, "created_at": a.created_at}
            for a in rows]
