"""Resumable chunked uploads.

POST /api/uploads                 create session {report_id, filename, content_type,
                                  total_size, sha256?, kind?} -> {upload_id, chunk_size,
                                  total_chunks, received}
PUT  /api/uploads/{id}/chunks/{n} raw chunk body (idempotent — re-PUT is fine)
GET  /api/uploads/{id}            resume info: which chunks are still missing
POST /api/uploads/{id}/complete   assemble -> checksum verify -> full media
                                  validation pipeline (same as direct upload)
DELETE /api/uploads/{id}          abort + cleanup

Abandoned sessions (>24h) are cleaned by cleanup_stale_sessions(), called from
the worker sweep. Chunks live in <storage>/_chunks/<upload_id>/ (private).
"""
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from ..audit import audit
from ..config import settings
from ..db import get_db
from ..models import Report, Role, UploadSession, User
from ..security import client_ip, get_current_user, rate_limit

log = logging.getLogger("civiclens.uploads")
router = APIRouter(prefix="/api/uploads", tags=["uploads"])

CHUNK_SIZE = 2 * 1024 * 1024   # 2 MB
ALLOWED_TYPES = set((settings.allowed_video_types + "," + settings.allowed_image_types).split(","))


def _chunk_dir(upload_id: str) -> str:
    d = os.path.join(settings.storage_dir, "_chunks", upload_id)
    os.makedirs(d, exist_ok=True)
    return d


def _received_set(sess: UploadSession) -> set[int]:
    return {int(x) for x in (sess.received or "").split(",") if x != ""}


class CreateSession(BaseModel):
    report_id: str
    filename: str = ""
    content_type: str
    total_size: int = Field(gt=0)
    sha256: str | None = None
    kind: str = "auto"


@router.post("", status_code=201)
def create_session(body: CreateSession, request: Request,
                   user: User | None = Depends(get_current_user),
                   db: DBSession = Depends(get_db)):
    rate_limit(f"upsess:{client_ip(request)}", 30, 3600)
    rpt = db.get(Report, body.report_id)
    if not rpt:
        raise HTTPException(404, "Report not found")
    if rpt.reporter_id and (not user or (user.id != rpt.reporter_id and
                                         user.role not in (Role.admin, Role.moderator, Role.org_staff))):
        raise HTTPException(403, "Not allowed to add media to this report")
    ctype = body.content_type.lower()
    if ctype not in ALLOWED_TYPES:
        raise HTTPException(415, f"Unsupported file type: {ctype}")
    max_mb = settings.max_video_mb if ctype.startswith("video/") else settings.max_image_mb
    if body.total_size > max_mb * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {max_mb} MB)")
    if len(rpt.media) >= settings.max_attachments:
        raise HTTPException(413, f"Maximum {settings.max_attachments} attachments per report")

    total_chunks = (body.total_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    sess = UploadSession(report_id=rpt.id, user_id=user.id if user else None,
                         filename=body.filename[:255], content_type=ctype,
                         kind=body.kind, total_size=body.total_size,
                         total_chunks=total_chunks, sha256=body.sha256)
    db.add(sess)
    db.commit()
    return {"upload_id": sess.id, "chunk_size": CHUNK_SIZE,
            "total_chunks": total_chunks, "received": []}


def _get_session(db, upload_id, user) -> UploadSession:
    sess = db.get(UploadSession, upload_id)
    if not sess or sess.status == "aborted":
        raise HTTPException(404, "Upload session not found")
    if sess.user_id and (not user or user.id != sess.user_id):
        raise HTTPException(403, "Not your upload session")
    return sess


@router.get("/{upload_id}")
def session_info(upload_id: str, user: User | None = Depends(get_current_user),
                 db: DBSession = Depends(get_db)):
    sess = _get_session(db, upload_id, user)
    rec = sorted(_received_set(sess))
    return {"upload_id": sess.id, "status": sess.status, "chunk_size": CHUNK_SIZE,
            "total_chunks": sess.total_chunks, "received": rec,
            "missing": [i for i in range(sess.total_chunks) if i not in set(rec)]}


@router.put("/{upload_id}/chunks/{index}")
async def put_chunk(upload_id: str, index: int, request: Request,
                    user: User | None = Depends(get_current_user),
                    db: DBSession = Depends(get_db)):
    sess = _get_session(db, upload_id, user)
    if sess.status != "pending":
        raise HTTPException(409, "Upload already completed")
    if not (0 <= index < sess.total_chunks):
        raise HTTPException(422, "Chunk index out of range")
    data = await request.body()
    if len(data) > CHUNK_SIZE:
        raise HTTPException(413, "Chunk exceeds chunk size")
    with open(os.path.join(_chunk_dir(sess.id), f"{index:06d}"), "wb") as f:
        f.write(data)
    rec = _received_set(sess)
    rec.add(index)                               # idempotent re-upload
    sess.received = ",".join(str(i) for i in sorted(rec))
    db.commit()
    return {"ok": True, "received": len(rec), "total": sess.total_chunks}


@router.post("/{upload_id}/complete")
def complete(upload_id: str, request: Request,
             user: User | None = Depends(get_current_user),
             db: DBSession = Depends(get_db)):
    sess = _get_session(db, upload_id, user)
    if sess.status == "complete":
        return {"ok": True, "already": True}     # idempotent completion
    rec = _received_set(sess)
    missing = [i for i in range(sess.total_chunks) if i not in rec]
    if missing:
        raise HTTPException(409, f"Missing chunks: {missing[:10]}"
                                 f"{'...' if len(missing) > 10 else ''}")

    # assemble
    cdir = _chunk_dir(sess.id)
    assembled = os.path.join(cdir, "assembled")
    with open(assembled, "wb") as out:
        for i in range(sess.total_chunks):
            with open(os.path.join(cdir, f"{i:06d}"), "rb") as part:
                shutil.copyfileobj(part, out)
    size = os.path.getsize(assembled)
    if size != sess.total_size:
        raise HTTPException(422, f"Assembled size {size} != declared {sess.total_size}")

    # checksum verification (when the client declared one)
    from ..integrity import file_sha256
    digest = file_sha256(assembled)
    if sess.sha256 and digest.lower() != sess.sha256.lower():
        raise HTTPException(422, "Checksum mismatch — upload corrupted, please retry")

    # run through the SAME validation + media pipeline as direct uploads
    from .reports import upload_media
    from fastapi import UploadFile
    import io
    with open(assembled, "rb") as f:
        payload = f.read()
    uf = UploadFile(file=io.BytesIO(payload), filename=sess.filename or "upload",
                    headers={"content-type": sess.content_type})
    result = upload_media(report_id=sess.report_id, request=request, file=uf,
                          kind=sess.kind, finalize=False, user=user, db=db)

    sess.status = "complete"
    db.commit()
    shutil.rmtree(cdir, ignore_errors=True)
    audit(db, user.id if user else None, "upload.chunked_complete", "upload_session",
          sess.id, detail=f"{sess.total_chunks} chunks, {size}b", ip=client_ip(request))
    return {"ok": True, "media": result, "sha256": digest}


@router.delete("/{upload_id}")
def abort(upload_id: str, user: User | None = Depends(get_current_user),
          db: DBSession = Depends(get_db)):
    sess = _get_session(db, upload_id, user)
    sess.status = "aborted"
    db.commit()
    shutil.rmtree(_chunk_dir(sess.id), ignore_errors=True)
    return {"ok": True}


def cleanup_stale_sessions(db: DBSession, max_age_hours: int = 24) -> int:
    """Called from the worker sweep: abort + delete chunks of abandoned sessions."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    stale = (db.query(UploadSession)
               .filter(UploadSession.status == "pending",
                       UploadSession.created_at < cutoff).all())
    for s in stale:
        s.status = "aborted"
        shutil.rmtree(os.path.join(settings.storage_dir, "_chunks", s.id),
                      ignore_errors=True)
    db.commit()
    return len(stale)
