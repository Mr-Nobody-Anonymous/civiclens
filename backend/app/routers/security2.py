"""P1 security maturity: email verification, TOTP MFA (+hashed backup codes),
session/device management. Pure-stdlib TOTP (RFC 6238) — no new dependencies."""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from ..audit import audit
from ..db import get_db
from ..models import EmailToken, Session as SessionModel, User
from ..notify import notify
from ..security import (client_ip, hash_password, rate_limit, require_user,
                        verify_password, COOKIE_NAME)

router = APIRouter(prefix="/api/security", tags=["security"])


# ============================ TOTP (RFC 6238) ============================
def totp_now(secret_b32: str, at: int | None = None, window: int = 0) -> str:
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    counter = int((at or time.time()) / 30) + window
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[19] & 0x0F
    code = (struct.unpack(">I", h[o:o+4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def totp_verify(secret_b32: str, code: str) -> bool:
    code = code.strip().replace(" ", "")
    return any(hmac.compare_digest(totp_now(secret_b32, window=w), code)
               for w in (-1, 0, 1))


# ============================ email verification ============================
@router.post("/verify-email/request")
def request_email_verification(request: Request, user: User = Depends(require_user),
                               db: DBSession = Depends(get_db)):
    rate_limit(f"everify:{user.id}", 5, 3600)
    if user.email_verified:
        return {"ok": True, "already_verified": True}
    tok = EmailToken(token=secrets.token_urlsafe(24), user_id=user.id,
                     expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    db.add(tok)
    db.commit()
    notify(db, user, "email_verify", "Verify your CivicLens email",
           f"Your verification code (valid 24h): {tok.token}")
    return {"ok": True}


class VerifyIn(BaseModel):
    token: str


@router.post("/verify-email/confirm")
def confirm_email(body: VerifyIn, user: User = Depends(require_user),
                  db: DBSession = Depends(get_db)):
    tok = db.get(EmailToken, body.token.strip())
    if not tok or tok.used or tok.user_id != user.id:
        raise HTTPException(400, "Invalid or already-used verification code")
    exp = tok.expires_at if tok.expires_at.tzinfo else tok.expires_at.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(400, "Verification code expired")
    tok.used = True
    user.email_verified = True
    db.commit()
    audit(db, user.id, "user.email_verified", "user", user.id)
    return {"ok": True, "email_verified": True}


# ============================ MFA ============================
@router.post("/mfa/setup")
def mfa_setup(user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    """Generate a TOTP secret + provisioning URI. Not enabled until confirmed."""
    if user.mfa_enabled:
        raise HTTPException(409, "MFA already enabled")
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    user.mfa_secret = secret
    db.commit()
    uri = (f"otpauth://totp/CivicLens%20Ethiopia:{user.email}"
           f"?secret={secret}&issuer=CivicLens%20Ethiopia")
    return {"secret": secret, "otpauth_uri": uri,
            "note": "Scan in an authenticator app, then confirm with a code."}


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@router.post("/mfa/enable")
def mfa_enable(body: MfaCode, request: Request, user: User = Depends(require_user),
               db: DBSession = Depends(get_db)):
    if not user.mfa_secret:
        raise HTTPException(409, "Run /mfa/setup first")
    if not totp_verify(user.mfa_secret, body.code):
        raise HTTPException(401, "Invalid authenticator code")
    # backup codes: shown ONCE, stored hashed
    plain = [secrets.token_hex(4) for _ in range(8)]
    user.mfa_backup_codes = json.dumps([hash_password(c) for c in plain])
    user.mfa_enabled = True
    db.commit()
    audit(db, user.id, "user.mfa_enabled", "user", user.id, ip=client_ip(request))
    return {"ok": True, "backup_codes": plain,
            "note": "Store these backup codes safely — they are shown only once."}


class MfaDisable(BaseModel):
    password: str
    code: str


@router.post("/mfa/disable")
def mfa_disable(body: MfaDisable, request: Request, user: User = Depends(require_user),
                db: DBSession = Depends(get_db)):
    if not user.mfa_enabled:
        raise HTTPException(409, "MFA not enabled")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Password incorrect")
    if not totp_verify(user.mfa_secret, body.code) and not _use_backup(db, user, body.code):
        raise HTTPException(401, "Invalid authenticator or backup code")
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_backup_codes = None
    db.commit()
    audit(db, user.id, "user.mfa_disabled", "user", user.id, ip=client_ip(request))
    return {"ok": True}


def _use_backup(db: DBSession, user: User, code: str) -> bool:
    try:
        hashes = json.loads(user.mfa_backup_codes or "[]")
    except Exception:
        return False
    for h in hashes:
        if verify_password(code.strip(), h):
            hashes.remove(h)                     # single use
            user.mfa_backup_codes = json.dumps(hashes)
            db.commit()
            return True
    return False


def mfa_check(db: DBSession, user: User, code: str | None) -> bool:
    """Called by the login flow when the account has MFA enabled."""
    if not user.mfa_enabled:
        return True
    if not code:
        return False
    return totp_verify(user.mfa_secret, code) or _use_backup(db, user, code)


# ============================ session / device management ============================
@router.get("/sessions")
def list_sessions(request: Request, user: User = Depends(require_user),
                  db: DBSession = Depends(get_db)):
    current = request.cookies.get(COOKIE_NAME)
    rows = (db.query(SessionModel).filter_by(user_id=user.id)
              .order_by(SessionModel.created_at.desc()).all())
    return [{"id": s.id[:12] + "…", "full_id_prefix": s.id[:12],
             "created_at": s.created_at, "expires_at": s.expires_at,
             "current": s.id == current} for s in rows]


@router.delete("/sessions/{id_prefix}")
def revoke_session(id_prefix: str, request: Request, user: User = Depends(require_user),
                   db: DBSession = Depends(get_db)):
    """Revoke one session by its 12-char prefix (never expose full tokens)."""
    if len(id_prefix) < 8:
        raise HTTPException(422, "Prefix too short")
    target = None
    for s in db.query(SessionModel).filter_by(user_id=user.id).all():
        if s.id.startswith(id_prefix):
            target = s
            break
    if not target:
        raise HTTPException(404, "Session not found")
    db.delete(target)
    db.commit()
    audit(db, user.id, "user.session_revoked", "session", id_prefix, ip=client_ip(request))
    return {"ok": True}
