"""Web Push subscription management.

POST   /api/push/subscribe          register this browser's subscription
DELETE /api/push/subscribe          remove it (by endpoint)
GET    /api/push/vapid-public-key   public key for the browser's PushManager
GET    /api/push/status             enabled? how many devices for this user?
POST   /api/push/test               send a test notification to my devices
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from ..audit import audit
from ..config import settings
from ..db import get_db
from ..models import PushSubscription, User
from ..push import push_enabled, send_push
from ..security import client_ip, rate_limit, require_user

router = APIRouter(prefix="/api/push", tags=["push"])


class SubscribeIn(BaseModel):
    endpoint: str = Field(min_length=8, max_length=2048)
    p256dh: str = Field(min_length=8, max_length=255)
    auth: str = Field(min_length=4, max_length=255)


@router.get("/vapid-public-key")
def vapid_public_key():
    if not push_enabled():
        raise HTTPException(503, "Web push is not configured on this server")
    return {"public_key": settings.vapid_public_key}


@router.get("/status")
def status(user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    n = db.query(PushSubscription).filter(PushSubscription.user_id == user.id).count()
    return {"enabled": push_enabled(), "devices": n}


@router.post("/subscribe", status_code=201)
def subscribe(body: SubscribeIn, request: Request,
              user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    if not push_enabled():
        raise HTTPException(503, "Web push is not configured on this server")
    rate_limit(f"push-sub:{user.id}", 20, 3600)
    existing = db.query(PushSubscription).filter(
        PushSubscription.user_id == user.id,
        PushSubscription.endpoint == body.endpoint).first()
    if existing:
        existing.p256dh, existing.auth = body.p256dh, body.auth
        db.commit()
        return {"id": existing.id, "updated": True}
    sub = PushSubscription(user_id=user.id, endpoint=body.endpoint,
                           p256dh=body.p256dh, auth=body.auth,
                           user_agent=(request.headers.get("user-agent") or "")[:255])
    db.add(sub)
    db.commit()
    audit(db, user.id, "push.subscribe", "push_subscription", sub.id, ip=client_ip(request))
    return {"id": sub.id, "updated": False}


@router.delete("/subscribe")
def unsubscribe(body: SubscribeIn, request: Request,
                user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    n = db.query(PushSubscription).filter(
        PushSubscription.user_id == user.id,
        PushSubscription.endpoint == body.endpoint).delete()
    db.commit()
    if n:
        audit(db, user.id, "push.unsubscribe", "push_subscription", None, ip=client_ip(request))
    return {"removed": n}


@router.post("/test")
def send_test(user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    if not push_enabled():
        raise HTTPException(503, "Web push is not configured on this server")
    rate_limit(f"push-test:{user.id}", 5, 3600)
    n = send_push(db, user, "CivicLens test notification",
                  "Push notifications are working on this device. 🎉")
    return {"delivered": n}
