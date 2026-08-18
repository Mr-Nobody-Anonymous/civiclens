"""Phase C APIs: subscriptions/following, community verification votes,
voice transcription proxy, city intelligence, notification preferences."""
import json
import math

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from ..audit import audit
from ..config import settings
from ..db import get_db
from ..models import (CommunityVote, Report, Subscription, User)
from ..security import client_ip, get_current_user, rate_limit, require_staff, require_user

router = APIRouter(prefix="/api", tags=["community"])


# ---------------------- subscriptions / following ----------------------
class SubIn(BaseModel):
    target_type: str = Field(pattern="^(report|cluster|category|area)$")
    target_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_m: int = Field(default=1000, ge=100, le=10000)
    label: str = ""


@router.post("/subscriptions", status_code=201)
def subscribe(body: SubIn, user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    if body.target_type == "area" and (body.latitude is None or body.longitude is None):
        raise HTTPException(422, "Area subscriptions need latitude/longitude")
    if body.target_type in ("report", "cluster", "category") and not body.target_id:
        raise HTTPException(422, f"{body.target_type} subscriptions need target_id")
    tid = body.target_id or f"{body.latitude:.3f},{body.longitude:.3f}"
    exists = db.query(Subscription).filter_by(
        user_id=user.id, target_type=body.target_type, target_id=tid).first()
    if exists:
        return {"id": exists.id, "already": True}
    sub = Subscription(user_id=user.id, target_type=body.target_type, target_id=tid,
                       latitude=body.latitude, longitude=body.longitude,
                       radius_m=body.radius_m, label=body.label[:120])
    db.add(sub)
    db.commit()
    return {"id": sub.id}


@router.get("/subscriptions")
def my_subscriptions(user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    rows = db.query(Subscription).filter_by(user_id=user.id).all()
    return [{"id": s.id, "target_type": s.target_type, "target_id": s.target_id,
             "label": s.label, "latitude": s.latitude, "longitude": s.longitude,
             "radius_m": s.radius_m, "created_at": s.created_at} for s in rows]


@router.delete("/subscriptions/{sub_id}")
def unsubscribe(sub_id: str, user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    s = db.get(Subscription, sub_id)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Subscription not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


def notify_subscribers(db: DBSession, report: Report):
    """Fan out to followers of the report's cluster/category/area.
    Called from the AI pipeline after classification. Deduplicated per user."""
    from ..notify import notify
    seen: set[str] = set()
    subs = db.query(Subscription).all()
    for s in subs:
        if s.user_id in seen or s.user_id == report.reporter_id:
            continue
        hit = False
        if s.target_type == "report" and s.target_id == report.id:
            hit = True
        elif s.target_type == "cluster" and report.cluster_id and s.target_id == report.cluster_id:
            hit = True
        elif s.target_type == "category" and s.target_id == report.category:
            hit = True
        elif s.target_type == "area" and s.latitude is not None and report.latitude is not None:
            R = 6371000.0
            p1, p2 = math.radians(report.latitude), math.radians(s.latitude)
            dp = math.radians(s.latitude - report.latitude)
            dl = math.radians(s.longitude - report.longitude)
            a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
            hit = 2 * R * math.asin(math.sqrt(a)) <= (s.radius_m or 1000)
        if hit:
            seen.add(s.user_id)
            u = db.get(User, s.user_id)
            notify(db, u, "followed_update",
                   f"New report near something you follow: {report.title[:60]}",
                   f"{report.category or 'Issue'} in {report.city or 'your area'}"
                   + (f" ({s.label})" if s.label else ""),
                   report_id=report.id)


# ---------------------- community verification ----------------------
class VoteIn(BaseModel):
    vote: str = Field(pattern="^(still_exists|resolved|not_sure)$")


@router.post("/reports/{report_id}/verify")
def community_verify(report_id: str, body: VoteIn, request: Request,
                     user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    """One vote per citizen per report; votes are EVIDENCE for humans, never
    authority — no status ever changes because of votes alone."""
    rate_limit(f"cvote:{user.id}", 20, 3600)
    rpt = db.get(Report, report_id)
    if not rpt or rpt.is_flagged:
        raise HTTPException(404, "Report not found")
    if rpt.reporter_id == user.id:
        raise HTTPException(422, "You cannot community-verify your own report")
    existing = db.query(CommunityVote).filter_by(report_id=report_id, user_id=user.id).first()
    if existing:
        existing.vote = body.vote      # citizens may change their mind
    else:
        db.add(CommunityVote(report_id=report_id, user_id=user.id, vote=body.vote))
    db.commit()
    audit(db, user.id, "community.verify", "report", report_id, detail=body.vote,
          ip=client_ip(request))
    return {"ok": True, **community_summary(report_id, db)}


@router.get("/reports/{report_id}/verification")
def community_summary_endpoint(report_id: str, db: DBSession = Depends(get_db),
                               user: User | None = Depends(get_current_user)):
    out = community_summary(report_id, db)
    if user:
        mine = db.query(CommunityVote).filter_by(report_id=report_id, user_id=user.id).first()
        out["my_vote"] = mine.vote if mine else None
    return out


def community_summary(report_id: str, db: DBSession) -> dict:
    """Anonymous public aggregation — individual voters are never exposed."""
    counts = dict(db.query(CommunityVote.vote, func.count(CommunityVote.id))
                    .filter(CommunityVote.report_id == report_id)
                    .group_by(CommunityVote.vote).all())
    return {"still_exists": counts.get("still_exists", 0),
            "resolved": counts.get("resolved", 0),
            "not_sure": counts.get("not_sure", 0),
            "note": "Community votes are evidence for reviewers, not authority."}


# ---------------------- voice reporting ----------------------
@router.post("/voice/transcribe")
async def voice_transcribe(request: Request,
                           user: User | None = Depends(get_current_user)):
    """Proxy raw audio to the local AI service; returns transcript + draft.
    Rate-limited; the citizen always reviews before submitting."""
    rate_limit(f"voice:{client_ip(request)}", 10, 3600)
    audio = await request.body()
    if len(audio) > 15 * 1024 * 1024:
        raise HTTPException(413, "Audio too large (max 15MB)")
    try:
        r = httpx.post(f"{settings.ai_url}/transcribe", content=audio, timeout=180)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError:
        raise HTTPException(503, "Voice transcription is temporarily unavailable — "
                                 "you can still type your report.")
    if "error" in data:
        raise HTTPException(422, data["error"])
    return data


# ---------------------- notification preferences ----------------------
DEFAULT_PREFS = {"status_changes": True, "organization_response": True,
                 "resolution": True, "reopened": True, "followed_updates": True,
                 "email_important": True}


class PrefsIn(BaseModel):
    prefs: dict


@router.get("/notification-preferences")
def get_prefs(user: User = Depends(require_user)):
    try:
        saved = json.loads(user.notif_prefs or "{}")
    except Exception:
        saved = {}
    return {**DEFAULT_PREFS, **saved}


@router.put("/notification-preferences")
def set_prefs(body: PrefsIn, user: User = Depends(require_user),
              db: DBSession = Depends(get_db)):
    clean = {k: bool(v) for k, v in body.prefs.items() if k in DEFAULT_PREFS}
    user.notif_prefs = json.dumps(clean)
    db.commit()
    return {**DEFAULT_PREFS, **clean}


# ---------------------- city intelligence ----------------------
@router.get("/intelligence/overview")
def intelligence_overview(city: str | None = None, db: DBSession = Depends(get_db),
                          staff: User = Depends(require_staff)):
    from ..intelligence import city_overview
    return city_overview(db, city)


@router.get("/intelligence/briefing")
def briefing(city: str | None = None, db: DBSession = Depends(get_db),
             staff: User = Depends(require_staff)):
    """The morning Civic Briefing — full pipeline convergence, advisory-labelled."""
    from ..briefing import civic_briefing
    return civic_briefing(db, city)


@router.get("/intelligence/hotspots")
def intelligence_hotspots(city: str | None = None, days: int = Query(30, le=180),
                          db: DBSession = Depends(get_db)):
    """Public: aggregated hotspots (coarse coordinates only — privacy safe)."""
    from ..intelligence import hotspots
    return hotspots(db, city, days)
