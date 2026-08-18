"""Auth: PBKDF2 password hashing, DB-backed sessions, RBAC deps, rate limiting."""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session as DBSession

from .config import settings
from .db import get_db
from .models import Role, Session as SessionModel, User

PBKDF2_ITERATIONS = 260_000
COOKIE_NAME = "cl_session"
CSRF_COOKIE = "cl_csrf"
CSRF_HEADER = "x-csrf-token"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, hexhash = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), hexhash)
    except Exception:
        return False


def create_session(db: DBSession, user: User, response: Response) -> str:
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    db.add(SessionModel(
        id=token, user_id=user.id, csrf_token=csrf,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours),
    ))
    # opportunistic cleanup of this user's expired sessions
    db.query(SessionModel).filter(
        SessionModel.user_id == user.id,
        SessionModel.expires_at < datetime.now(timezone.utc)).delete()
    db.commit()
    secure = settings.env == "production"
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax",
                        secure=secure, max_age=settings.session_ttl_hours * 3600, path="/")
    # CSRF cookie is intentionally NOT HttpOnly (double-submit pattern: JS must read it)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, samesite="lax",
                        secure=secure, max_age=settings.session_ttl_hours * 3600, path="/")
    return token


def revoke_all_sessions(db: DBSession, user: User):
    db.query(SessionModel).filter(SessionModel.user_id == user.id).delete()
    db.commit()


def destroy_session(db: DBSession, request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.query(SessionModel).filter(SessionModel.id == token).delete()
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def get_current_user(request: Request, db: DBSession = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    sess = db.query(SessionModel).filter(SessionModel.id == token).first()
    if not sess:
        return None
    exp = sess.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        db.delete(sess)
        db.commit()
        return None
    user = db.query(User).filter(User.id == sess.user_id, User.is_active == True).first()  # noqa: E712
    return user


def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


def require_roles(*roles: Role):
    def dep(user: User = Depends(require_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return dep


require_admin = require_roles(Role.admin)
require_staff = require_roles(Role.admin, Role.moderator)          # admin console
require_org = require_roles(Role.admin, Role.org_staff)            # org portal
require_triage = require_roles(Role.admin, Role.moderator, Role.org_staff)  # priority queue


# ------------------------- simple in-memory rate limiter -------------------------
_buckets: dict = defaultdict(deque)


def rate_limit(key: str, limit: int, window_s: int):
    """Sliding-window limiter. In multi-instance prod, swap for Redis."""
    q = _buckets[key]
    cutoff = time.time() - window_s
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many requests — please slow down.")
    q.append(time.time())


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


# ------------------------- CSRF (double-submit cookie) -------------------------
CSRF_EXEMPT = {"/api/auth/login", "/api/auth/register", "/api/auth/forgot-password",
               "/api/auth/reset-password"}


async def csrf_protect(request: Request, db: DBSession):
    """For state-changing requests from authenticated sessions, require the
    X-CSRF-Token header to match the session's stored token."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if request.url.path in CSRF_EXEMPT:
        return
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return  # anonymous requests can't be CSRF'd into a session action
    sess = db.query(SessionModel).filter(SessionModel.id == token).first()
    if not sess:
        return
    header = request.headers.get(CSRF_HEADER, "")
    if not sess.csrf_token or not hmac.compare_digest(header, sess.csrf_token):
        raise HTTPException(403, "CSRF token missing or invalid")


# ------------------------- login lockout -------------------------
def check_lockout(db: DBSession, email: str):
    from .models import LoginAttempt
    la = db.get(LoginAttempt, email.lower())
    if la and la.locked_until:
        lu = la.locked_until if la.locked_until.tzinfo else la.locked_until.replace(tzinfo=timezone.utc)
        if lu > datetime.now(timezone.utc):
            raise HTTPException(429, "Account temporarily locked due to repeated failed logins. Try again later.")


def record_login_result(db: DBSession, email: str, success: bool):
    from .models import LoginAttempt
    email = email.lower()
    la = db.get(LoginAttempt, email)
    if success:
        if la:
            db.delete(la)
            db.commit()
        return
    if not la:
        la = LoginAttempt(email=email, failures=0)
        db.add(la)
    la.failures = (la.failures or 0) + 1
    if la.failures >= settings.login_max_failures:
        la.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.login_lock_minutes)
        la.failures = 0
    db.commit()
