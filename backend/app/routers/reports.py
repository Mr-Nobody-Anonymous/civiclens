import math
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Query,
                     Request, UploadFile)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession

from ..audit import audit
from ..config import settings
from ..db import get_db
from .. import media as mediaproc
from ..jobs import enqueue
from ..models import (OPEN_STATUSES, CATEGORIES, OrganizationUser, Report,
                      ReportAIAnalysis, ReportComment, ReportMedia,
                      ReportStatus, ReportStatusHistory, ReportAssignment,
                      Role, User)
from ..notify import notify
from ..state_machine import transition
from ..schemas import (AssignmentPatch, CommentIn, CorrectionPatch, FlagIn,
                       ReportCreate, StatusPatch)
from ..security import (client_ip, get_current_user, rate_limit, require_user,
                        require_staff, require_triage)
from ..serializers import report_privileged, report_public
from ..storage import new_key, storage

router = APIRouter(prefix="/api/reports", tags=["reports"])

VIDEO_TYPES = set(settings.allowed_video_types.split(","))
IMAGE_TYPES = set(settings.allowed_image_types.split(","))
VIDEO_EXT = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}
IMAGE_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

# Magic-byte sniffing so a renamed .exe can't sneak in with a fake MIME type
MAGIC = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG"],
    "image/webp": [b"RIFF"],
    "video/mp4": [b"ftyp"],       # checked at offset 4
    "video/quicktime": [b"ftyp"],
    "video/webm": [b"\x1a\x45\xdf\xa3"],
}


def _sniff_ok(head: bytes, ctype: str) -> bool:
    sigs = MAGIC.get(ctype, [])
    if not sigs:
        return False
    if ctype in ("video/mp4", "video/quicktime"):
        return b"ftyp" in head[:32]
    return any(head.startswith(s) for s in sigs)


def _haversine_m(lat1, lng1, lat2, lng2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _find_possible_duplicate(db: DBSession, rpt: Report) -> Optional[Report]:
    if rpt.latitude is None or rpt.longitude is None:
        return None
    window = datetime.now(timezone.utc) - timedelta(days=settings.duplicate_window_days)
    near = (db.query(Report)
              .filter(Report.id != rpt.id,
                      Report.created_at >= window,
                      Report.status.in_(OPEN_STATUSES),
                      Report.latitude.between(rpt.latitude - 0.01, rpt.latitude + 0.01),
                      Report.longitude.between(rpt.longitude - 0.01, rpt.longitude + 0.01))
              .limit(200).all())
    words = set(w for w in (rpt.title + " " + rpt.description).lower().split() if len(w) > 3)
    for other in near:
        if _haversine_m(rpt.latitude, rpt.longitude, other.latitude, other.longitude) > settings.duplicate_radius_m:
            continue
        ow = set(w for w in (other.title + " " + other.description).lower().split() if len(w) > 3)
        if words and ow and len(words & ow) / max(1, len(words | ow)) > 0.25:
            return other
        if rpt.user_category and rpt.user_category == (other.user_category or other.category):
            return other
    return None


# --------------------------------------------------------------------------
# CREATE
# --------------------------------------------------------------------------
@router.post("", status_code=201)
def create_report(body: ReportCreate, request: Request,
                  user: Optional[User] = Depends(get_current_user),
                  db: DBSession = Depends(get_db)):
    ip = client_ip(request)
    rate_limit(f"report:{ip}", settings.rate_limit_reports_per_hour, 3600)

    # lightweight anti-bot check for anonymous submissions (simple arithmetic captcha)
    if not user:
        if body.captcha_a is None or body.captcha_answer is None or \
                body.captcha_a + (body.captcha_b or 0) != body.captcha_answer:
            raise HTTPException(400, "Captcha verification failed")

    if body.category and body.category not in CATEGORIES:
        raise HTTPException(400, "Unknown category")

    rpt = Report(
        reporter_id=user.id if user else None,
        title=body.title.strip(), description=body.description.strip(),
        comments=body.comments, user_category=body.category, category=body.category,
        city=body.city or settings.cities.split(",")[0],
        latitude=body.latitude, longitude=body.longitude, address=body.address,
        status=ReportStatus.submitted,
    )
    db.add(rpt)
    db.commit()
    db.add(ReportStatusHistory(report_id=rpt.id, from_status=None,
                               to_status=ReportStatus.submitted.value, note="Report submitted"))
    db.commit()

    dup = _find_possible_duplicate(db, rpt)
    audit(db, user.id if user else None, "report.create", "report", rpt.id, ip=ip)
    if user:
        notify(db, user, "received", f"Report {rpt.public_code} received",
               "Thank you! Your report has been received. Attach evidence and it will be "
               "analysed automatically.", report_id=rpt.id)

    out = report_public(rpt)
    out["possible_duplicate"] = dup is not None
    if dup:
        out["duplicate_of_code"] = dup.public_code
    return out


# --------------------------------------------------------------------------
# MEDIA upload  (multipart; browser shows progress via XHR)
# --------------------------------------------------------------------------
@router.post("/{report_id}/media", status_code=201)
def upload_media(report_id: str, request: Request,
                 file: UploadFile = File(...),
                 kind: str = Form("auto"),
                 finalize: bool = Form(False),
                 user: Optional[User] = Depends(get_current_user),
                 db: DBSession = Depends(get_db)):
    rate_limit(f"media:{client_ip(request)}", 30, 3600)
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    # only the reporter (or staff / anonymous session that just created it) may add evidence
    if rpt.reporter_id and (not user or (user.id != rpt.reporter_id and
                                         user.role not in (Role.admin, Role.moderator, Role.org_staff))):
        raise HTTPException(403, "Not allowed to add media to this report")

    # attachment cap per report
    if len(rpt.media) >= settings.max_attachments:
        raise HTTPException(413, f"Maximum {settings.max_attachments} attachments per report")

    ctype = (file.content_type or "").lower()
    if kind == "resolution":
        if not user or user.role not in (Role.admin, Role.org_staff):
            raise HTTPException(403, "Only organization staff can upload resolution evidence")
        media_kind = "resolution"
        allowed = VIDEO_TYPES | IMAGE_TYPES
    elif ctype in VIDEO_TYPES:
        media_kind, allowed = "video", VIDEO_TYPES
    elif ctype in IMAGE_TYPES:
        media_kind, allowed = "image", IMAGE_TYPES
    else:
        raise HTTPException(415, f"Unsupported file type: {ctype}")
    if ctype not in allowed:
        raise HTTPException(415, f"Unsupported file type: {ctype}")

    # extension must agree with declared MIME (defence in depth; storage key is
    # always server-generated so the user filename is never used as a path)
    fname = (file.filename or "").lower()
    expected_ext = VIDEO_EXT.get(ctype) or IMAGE_EXT.get(ctype) or ""
    ext_ok = {".jpg": (".jpg", ".jpeg"), ".mp4": (".mp4", ".m4v")}.get(expected_ext, (expected_ext,))
    if fname and "." in fname and not fname.endswith(ext_ok):
        raise HTTPException(415, "File extension does not match its content type")

    max_bytes = (settings.max_video_mb if ctype in VIDEO_TYPES else settings.max_image_mb) * 1024 * 1024
    head = file.file.read(64)
    if not _sniff_ok(head, ctype):
        raise HTTPException(415, "File content does not match its declared type")
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    if size > max_bytes:
        raise HTTPException(413, f"File too large (max {max_bytes // (1024*1024)} MB)")
    if size < 64:
        raise HTTPException(422, "File is empty or truncated")
    file.file.seek(0)

    key = new_key(rpt.id, media_kind, expected_ext)
    storage.save(key, file.file)

    # deep validation via ffprobe: reject corrupt media / over-long videos
    try:
        local_probe = storage.path(key)
        meta_check = mediaproc.probe(local_probe)
        if ctype in VIDEO_TYPES:
            if not meta_check.get("codec"):
                storage.delete(key)
                raise HTTPException(422, "Video appears corrupt or unreadable")
            if (meta_check.get("duration_s") or 0) > settings.max_video_seconds:
                storage.delete(key)
                raise HTTPException(413,
                    f"Video too long (max {settings.max_video_seconds // 60} minutes)")
    except HTTPException:
        raise
    except Exception:
        pass  # probe hiccup: file already passed magic-byte + size checks

    m = ReportMedia(report_id=rpt.id, kind=media_kind, storage_key=key,
                    content_type=ctype, size_bytes=size,
                    original_name=(file.filename or "")[:255],
                    uploaded_by=user.id if user else None)

    # metadata + thumbnail via ffmpeg
    try:
        local = storage.path(key)
        if ctype in VIDEO_TYPES:
            meta = mediaproc.probe(local)
            m.duration_s, m.width, m.height = meta.get("duration_s"), meta.get("width"), meta.get("height")
            tk = key + ".thumb.jpg"
            tpath = local + ".thumb.jpg"
            if mediaproc.make_video_thumbnail(local, tpath):
                if os.path.abspath(tpath) != os.path.abspath(storage.path(tk)):
                    with open(tpath, "rb") as tf:
                        storage.save(tk, tf)
                m.thumb_key = tk
        else:
            tk = key + ".thumb.jpg"
            tpath = local + ".thumb.jpg"
            if mediaproc.make_image_thumbnail(local, tpath):
                if os.path.abspath(tpath) != os.path.abspath(storage.path(tk)):
                    with open(tpath, "rb") as tf:
                        storage.save(tk, tf)
                m.thumb_key = tk
    except Exception:
        pass

    db.add(m)
    db.commit()
    audit(db, user.id if user else None, "media.upload", "report_media", m.id,
          detail=f"{media_kind} {size}b", ip=client_ip(request))

    if finalize:
        enqueue("process_report", report_id=rpt.id)

    return {"id": m.id, "kind": m.kind, "size_bytes": size, "has_thumb": bool(m.thumb_key)}


@router.post("/{report_id}/finalize")
def finalize_report(report_id: str, user: Optional[User] = Depends(get_current_user),
                    db: DBSession = Depends(get_db)):
    """Kick off async AI pipeline once the reporter finished uploading evidence."""
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    if rpt.status != ReportStatus.submitted or rpt.processing_state in ("queued", "processing", "done"):
        return {"ok": True, "status": rpt.status.value}   # idempotent — no duplicate jobs
    rpt.processing_state = "queued"
    db.commit()
    enqueue("process_report", report_id=rpt.id)
    return {"ok": True, "status": "queued"}


# --------------------------------------------------------------------------
# LIST / DETAIL (public, privacy-safe)
# --------------------------------------------------------------------------
@router.get("")
def list_reports(db: DBSession = Depends(get_db),
                 q: Optional[str] = None,
                 category: Optional[str] = None,
                 status: Optional[str] = None,
                 severity: Optional[int] = Query(None, ge=1, le=5),
                 min_severity: Optional[int] = Query(None, ge=1, le=5),
                 city: Optional[str] = None,
                 mine: bool = False,
                 sort: str = "recent",
                 page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100),
                 user: Optional[User] = Depends(get_current_user)):
    qry = db.query(Report)
    if mine:
        if not user:
            raise HTTPException(401, "Login required")
        qry = qry.filter(Report.reporter_id == user.id)
    else:
        qry = qry.filter(Report.is_flagged == False)  # noqa: E712  hide flagged from public
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
    if severity:
        qry = qry.filter(Report.severity == severity)
    if min_severity:
        qry = qry.filter(Report.severity >= min_severity)
    if city:
        qry = qry.filter(Report.city == city)

    total = qry.count()
    if sort == "severity":
        qry = qry.order_by(Report.severity.desc().nullslast(), Report.created_at.desc())
    else:
        qry = qry.order_by(Report.created_at.desc())
    rows = qry.offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [report_public(r) for r in rows]}


@router.get("/map")
def map_reports(db: DBSession = Depends(get_db),
                category: Optional[str] = None,
                min_severity: Optional[int] = None,
                status: Optional[str] = None):
    qry = db.query(Report).filter(Report.latitude.isnot(None), Report.is_flagged == False)  # noqa: E712
    if category:
        qry = qry.filter(Report.category == category)
    if min_severity:
        qry = qry.filter(Report.severity >= min_severity)
    if status:
        qry = qry.filter(Report.status == ReportStatus(status))
    rows = qry.order_by(Report.created_at.desc()).limit(1000).all()
    return [{"id": r.id, "code": r.public_code, "title": r.title, "category": r.category,
             "severity": r.severity, "status": r.status.value,
             "lat": round(r.latitude, 4), "lng": round(r.longitude, 4),
             "city": r.city, "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


@router.get("/priority")
def priority_queue(db: DBSession = Depends(get_db), user: User = Depends(require_triage)):
    qry = db.query(Report).filter(Report.status.in_(OPEN_STATUSES))
    if user.role == Role.org_staff:
        link = db.query(OrganizationUser).filter(OrganizationUser.user_id == user.id).first()
        if not link:
            raise HTTPException(403, "No organization membership")
        qry = qry.filter(Report.organization_id == link.organization_id)
    rows = (qry.order_by(Report.severity.desc().nullslast(), Report.created_at.asc())
               .limit(100).all())
    return [report_privileged(r) for r in rows]


@router.get("/{report_id}")
def get_report(report_id: str, db: DBSession = Depends(get_db),
               user: Optional[User] = Depends(get_current_user)):
    rpt = db.get(Report, report_id) or \
        db.query(Report).filter(Report.public_code == report_id.upper()).first()
    if not rpt:
        raise HTTPException(404, "Report not found")
    dup = db.get(Report, rpt.duplicate_of_id) if rpt.duplicate_of_id else None
    privileged = user and (
        user.role in (Role.admin, Role.moderator) or
        (rpt.reporter_id and user.id == rpt.reporter_id) or
        (user.role == Role.org_staff and rpt.organization_id and
         db.query(OrganizationUser).filter(OrganizationUser.user_id == user.id,
                                           OrganizationUser.organization_id == rpt.organization_id).first())
    )
    if rpt.is_flagged and not privileged:
        raise HTTPException(404, "Report not found")
    data = report_privileged(rpt, dup.public_code if dup else None) if privileged \
        else report_public(rpt, dup.public_code if dup else None)

    # public timeline (no internal notes)
    hist = (db.query(ReportStatusHistory).filter(ReportStatusHistory.report_id == rpt.id)
              .order_by(ReportStatusHistory.created_at.asc()).all())
    data["history"] = [{"to_status": h.to_status, "note": h.note if privileged else None,
                        "created_at": h.created_at} for h in hist]
    comments = (db.query(ReportComment).filter(ReportComment.report_id == rpt.id)
                  .order_by(ReportComment.created_at.asc()).all())
    data["comments"] = [
        {"id": c.id, "body": c.body, "internal": c.internal,
         "author": (c.user.name if c.user else "Anonymous"), "created_at": c.created_at}
        for c in comments if privileged or not c.internal
    ]
    return data


@router.get("/{report_id}/analysis")
def get_analysis(report_id: str, db: DBSession = Depends(get_db)):
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    if not rpt.ai:
        return {"status": rpt.status.value, "analysis": None}
    from ..serializers import ai_out
    return {"status": rpt.status.value, "analysis": ai_out(rpt.ai)}


# --------------------------------------------------------------------------
# SECURE MEDIA STREAMING — access-controlled; storage never exposed directly
# --------------------------------------------------------------------------
def _can_view_media(db, user, rpt: Report) -> bool:
    """Evidence on publicly listed reports is viewable (that's the product's
    transparency model); flagged/hidden reports restrict media to the reporter,
    moderators/admins, and the assigned organization ONLY."""
    if not rpt.is_flagged:
        return True
    if not user:
        return False
    if user.role in (Role.admin, Role.moderator):
        return True
    if rpt.reporter_id and user.id == rpt.reporter_id:
        return True
    if user.role == Role.org_staff and rpt.organization_id:
        return db.query(OrganizationUser).filter(
            OrganizationUser.user_id == user.id,
            OrganizationUser.organization_id == rpt.organization_id).first() is not None
    return False


@router.get("/{report_id}/media/{media_id}/file")
def stream_media(report_id: str, media_id: str, request: Request,
                 db: DBSession = Depends(get_db),
                 user: Optional[User] = Depends(get_current_user)):
    m = db.get(ReportMedia, media_id)
    if not m or m.report_id != report_id:
        raise HTTPException(404, "Media not found")
    rpt = db.get(Report, report_id)
    if not _can_view_media(db, user, rpt):
        raise HTTPException(403, "Not authorised to view this media")
    path = storage.path(m.storage_key)
    if not os.path.exists(path):
        raise HTTPException(404, "File missing")

    # HTTP Range support so <video> can seek
    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")
    if range_header and m.kind in ("video", "resolution"):
        try:
            start_s, end_s = range_header.replace("bytes=", "").split("-")
            start = int(start_s)
            end = int(end_s) if end_s else min(start + 1024 * 1024 * 2, file_size - 1)
        except Exception:
            start, end = 0, file_size - 1
        end = min(end, file_size - 1)

        def iter_range():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        return StreamingResponse(iter_range(), status_code=206, media_type=m.content_type, headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes", "Content-Length": str(end - start + 1),
        })
    return FileResponse(path, media_type=m.content_type)


@router.get("/{report_id}/media/{media_id}/thumb")
def media_thumb(report_id: str, media_id: str, db: DBSession = Depends(get_db),
                user: Optional[User] = Depends(get_current_user)):
    m = db.get(ReportMedia, media_id)
    if not m or m.report_id != report_id or not m.thumb_key:
        raise HTTPException(404, "Thumbnail not found")
    rpt = db.get(Report, report_id)
    if not _can_view_media(db, user, rpt):
        raise HTTPException(403, "Not authorised")
    return FileResponse(storage.path(m.thumb_key), media_type="image/jpeg")


# --------------------------------------------------------------------------
# STAFF ACTIONS: status, assignment, AI correction, comments, flags
# --------------------------------------------------------------------------
def _org_of(db, user) -> Optional[str]:
    link = db.query(OrganizationUser).filter(OrganizationUser.user_id == user.id).first()
    return link.organization_id if link else None


def _can_manage(db, user: User, rpt: Report) -> bool:
    if user.role in (Role.admin, Role.moderator):
        return True
    if user.role == Role.org_staff:
        return rpt.organization_id is not None and rpt.organization_id == _org_of(db, user)
    return False


@router.patch("/{report_id}/status")
def patch_status(report_id: str, body: StatusPatch, request: Request,
                 user: User = Depends(require_triage), db: DBSession = Depends(get_db)):
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    if not _can_manage(db, user, rpt):
        raise HTTPException(403, "Not allowed for this report")
    try:
        new_status = ReportStatus(body.status)
    except ValueError:
        raise HTTPException(400, "Unknown status")
    if new_status == ReportStatus.rejected and not (body.note or "").strip():
        raise HTTPException(422, "A reason note is required when rejecting a report")

    transition(db, rpt, new_status, actor=user, note=body.note or "")
    audit(db, user.id, "report.status", "report", rpt.id,
          detail=f"-> {new_status.value} ({body.note or ''})", ip=client_ip(request))
    return {"ok": True, "status": new_status.value}


@router.post("/{report_id}/reopen")
def reopen_report(report_id: str, request: Request, reason: str = "",
                  user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    """Reporter (or staff) can reopen/dispute a resolved or rejected report."""
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    is_reporter = rpt.reporter_id and user.id == rpt.reporter_id
    if not is_reporter and not _can_manage(db, user, rpt):
        raise HTTPException(403, "Only the reporter or staff can reopen a report")
    if rpt.status not in (ReportStatus.resolved, ReportStatus.rejected):
        raise HTTPException(409, "Only resolved or rejected reports can be reopened")
    transition(db, rpt, ReportStatus.reopened, actor=user,
               note=reason or ("Reopened by reporter" if is_reporter else "Reopened by staff"))
    audit(db, user.id, "report.reopen", "report", rpt.id, detail=reason, ip=client_ip(request))
    return {"ok": True, "status": rpt.status.value}


@router.post("/{report_id}/retry-analysis")
def retry_analysis_endpoint(report_id: str, user: User = Depends(require_staff),
                            db: DBSession = Depends(get_db)):
    """Staff can explicitly re-run AI analysis (e.g. after AI outage)."""
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    enqueue("retry_analysis", report_id=rpt.id)
    audit(db, user.id, "report.retry_analysis", "report", rpt.id)
    return {"ok": True, "processing_state": "queued"}


@router.patch("/{report_id}/assignment")
def patch_assignment(report_id: str, body: AssignmentPatch, request: Request,
                     user: User = Depends(require_triage), db: DBSession = Depends(get_db)):
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")

    if body.accept is not None:  # org accepting/declining its assignment
        if not _can_manage(db, user, rpt):
            raise HTTPException(403, "Not allowed")
        a = (db.query(ReportAssignment).filter(ReportAssignment.report_id == rpt.id)
               .order_by(ReportAssignment.created_at.desc()).first())
        if a:
            a.accepted = body.accept
            db.commit()
        if body.accept and rpt.status == ReportStatus.under_review:
            transition(db, rpt, ReportStatus.assigned, actor=user, note="Assignment accepted")
        audit(db, user.id, "report.assignment_accept" if body.accept else "report.assignment_decline",
              "report", rpt.id)
        return {"ok": True}

    # re-routing to another org: admin/moderator only (never trust user-picked orgs)
    if user.role not in (Role.admin, Role.moderator):
        raise HTTPException(403, "Only admins/moderators can re-route reports")
    from ..models import Organization
    org = db.get(Organization, body.organization_id) if body.organization_id else None
    if body.organization_id and not org:
        raise HTTPException(404, "Organization not found")
    rpt.organization_id = org.id if org else None
    rpt.routing_state = "manual" if org else "needs_manual_routing"
    db.add(ReportAssignment(report_id=rpt.id, organization_id=org.id if org else None,
                            assignee_user_id=body.assignee_user_id,
                            assigned_by=user.id, source="manual", note=body.note))
    db.commit()
    if org and rpt.status in (ReportStatus.under_review, ReportStatus.submitted,
                              ReportStatus.ai_analysis, ReportStatus.reopened):
        transition(db, rpt, ReportStatus.assigned, actor=user,
                   note=f"Assigned to {org.name}", force=True)
    audit(db, user.id, "report.assign", "report", rpt.id,
          detail=org.name if org else "unassigned", ip=client_ip(request))
    if rpt.reporter_id and org:
        notify(db, db.get(User, rpt.reporter_id), "assigned",
               f"Report {rpt.public_code} assigned to {org.name}", "", report_id=rpt.id)
    return {"ok": True}


@router.patch("/{report_id}/correction")
def correct_ai(report_id: str, body: CorrectionPatch, request: Request,
               user: User = Depends(require_staff), db: DBSession = Depends(get_db)):
    """Admin/moderator corrects AI classification (AI is a recommendation, not truth)."""
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    if body.category:
        if body.category not in CATEGORIES:
            raise HTTPException(400, "Unknown category")
        rpt.category = body.category
    if body.issue_type:
        rpt.issue_type = body.issue_type
    if body.severity:
        rpt.severity = body.severity
    rpt.human_confirmed = True   # later automated processing must never overwrite this
    if rpt.ai:
        rpt.ai.corrected_by = user.id
        rpt.ai.corrected_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, user.id, "report.ai_correction", "report", rpt.id,
          detail=f"cat={body.category} sev={body.severity} note={body.note or ''}",
          ip=client_ip(request))
    return {"ok": True}


@router.post("/{report_id}/comments", status_code=201)
def add_comment(report_id: str, body: CommentIn, user: User = Depends(require_user),
                db: DBSession = Depends(get_db)):
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    internal = body.internal
    if internal and not _can_manage(db, user, rpt):
        raise HTTPException(403, "Internal notes are staff-only")
    c = ReportComment(report_id=rpt.id, user_id=user.id, body=body.body, internal=internal)
    db.add(c)
    db.commit()
    return {"id": c.id, "created_at": c.created_at}


@router.post("/{report_id}/flag")
def flag_report(report_id: str, body: FlagIn, request: Request,
                user: Optional[User] = Depends(get_current_user),
                db: DBSession = Depends(get_db)):
    """Anyone can flag spam/abuse; staff see flagged reports in moderation."""
    rate_limit(f"flag:{client_ip(request)}", 10, 3600)
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    rpt.is_flagged = True
    rpt.flag_reason = body.reason
    db.commit()
    audit(db, user.id if user else None, "report.flag", "report", rpt.id,
          detail=body.reason, ip=client_ip(request))
    return {"ok": True}


@router.patch("/{report_id}/unflag")
def unflag(report_id: str, user: User = Depends(require_staff), db: DBSession = Depends(get_db)):
    rpt = db.get(Report, report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    rpt.is_flagged = False
    rpt.flag_reason = None
    db.commit()
    audit(db, user.id, "report.unflag", "report", rpt.id)
    return {"ok": True}


@router.patch("/{report_id}/duplicate")
def mark_duplicate(report_id: str, of_code: str, user: User = Depends(require_staff),
                   db: DBSession = Depends(get_db)):
    rpt = db.get(Report, report_id)
    orig = db.query(Report).filter(Report.public_code == of_code.upper()).first()
    if not rpt or not orig:
        raise HTTPException(404, "Report not found")
    if rpt.id == orig.id:
        raise HTTPException(422, "A report cannot be a duplicate of itself")
    rpt.duplicate_of_id = orig.id
    db.commit()
    transition(db, rpt, ReportStatus.duplicate, actor=user,
               note=f"Duplicate of {orig.public_code}")
    audit(db, user.id, "report.duplicate", "report", rpt.id, detail=orig.public_code)
    # tell the reporter their report was linked, not lost
    if rpt.reporter_id:
        notify(db, db.get(User, rpt.reporter_id), "duplicate",
               f"Report {rpt.public_code} linked to an existing report",
               f"Your report describes the same issue as {orig.public_code}; progress will be "
               "tracked there. Nothing was deleted.", report_id=rpt.id)
    return {"ok": True}
