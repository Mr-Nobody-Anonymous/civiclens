"""Web Push (VAPID) channel.

Design mirrors the e-mail channel: best-effort, never fatal, circuit-broken.
Push is OFF unless CL_VAPID_PUBLIC_KEY / CL_VAPID_PRIVATE_KEY are set.

Key generation (one-time, per deployment):
    python -m app.push --generate-keys
prints the two env values. The public key is served to browsers via
GET /api/push/vapid-public-key; the private key never leaves the server.

Dead subscriptions (404/410 from the push service) are pruned automatically.
"""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession

from .config import settings
from .models import PushSubscription, User

log = logging.getLogger("civiclens.push")


def push_enabled() -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def _webpush_available() -> bool:
    try:
        import pywebpush  # noqa: F401
        return True
    except ImportError:
        return False


def send_push(db: DBSession, user: User, title: str, body: str,
              report_id: str | None = None) -> int:
    """Send to every registered device of `user`. Returns delivered count.
    Never raises — push is a bonus channel on top of in-app + SSE + email."""
    if not push_enabled() or not _webpush_available():
        return 0
    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user.id).all()
    if not subs:
        return 0

    from pywebpush import webpush, WebPushException
    payload = json.dumps({
        "title": title, "body": body, "report_id": report_id,
        "url": f"/reports/{report_id}" if report_id else "/notifications",
    })
    delivered = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=3600,
            )
            sub.last_used_at = datetime.now(timezone.utc)
            delivered += 1
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                log.info("pruning dead push subscription %s (HTTP %s)", sub.id, status)
                db.delete(sub)   # browser unsubscribed / endpoint expired
            else:
                log.warning("push send failed for sub %s: %s", sub.id, e)
        except Exception as e:
            log.warning("push send error for sub %s: %s", sub.id, e)
    db.commit()
    return delivered


def generate_vapid_keys() -> dict:
    """Generate a fresh VAPID key pair (P-256), output as base64url strings
    in the exact format pywebpush expects."""
    import base64
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    priv = ec.generate_private_key(ec.SECP256R1())
    priv_raw = priv.private_numbers().private_value.to_bytes(32, "big")
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

    b64u = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    return {"public_key": b64u(pub_raw), "private_key": b64u(priv_raw)}


if __name__ == "__main__":
    import sys
    if "--generate-keys" in sys.argv:
        keys = generate_vapid_keys()
        print("# Add to your environment (.env):")
        print(f"CL_VAPID_PUBLIC_KEY={keys['public_key']}")
        print(f"CL_VAPID_PRIVATE_KEY={keys['private_key']}")
        print("CL_VAPID_SUBJECT=mailto:you@example.com")
    else:
        print(__doc__)
