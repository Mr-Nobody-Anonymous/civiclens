import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as DBSession

from ..audit import audit
from ..config import settings
from ..db import get_db
from ..models import OrganizationUser, PasswordReset, Role, User
from ..schemas import LoginIn, RegisterIn, SettingsIn, UserOut
from ..security import (check_lockout, client_ip, create_session,
                        destroy_session, get_current_user, hash_password,
                        rate_limit, record_login_result, revoke_all_sessions,
                        require_user, verify_password)

log = logging.getLogger("civiclens.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


def _user_out(db: DBSession, user: User) -> dict:
    link = db.query(OrganizationUser).filter(OrganizationUser.user_id == user.id).first()
    return {
        "id": user.id, "name": user.name, "email": user.email, "role": user.role.value,
        "language": user.language, "city": user.city,
        "email_notifications": user.email_notifications,
        "organization_id": link.organization_id if link else None,
        "organization_name": link.organization.name if link else None,
    }


@router.post("/register", response_model=UserOut)
def register(body: RegisterIn, request: Request, response: Response,
             db: DBSession = Depends(get_db)):
    rate_limit(f"reg:{client_ip(request)}", settings.rate_limit_auth_per_minute, 60)
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=body.email.lower(), name=body.name.strip(),
                password_hash=hash_password(body.password), phone=body.phone,
                language=body.language, city=body.city, role=Role.citizen)
    db.add(user)
    db.commit()
    create_session(db, user, response)
    audit(db, user.id, "user.register", "user", user.id, ip=client_ip(request))
    return _user_out(db, user)


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: DBSession = Depends(get_db)):
    rate_limit(f"login:{client_ip(request)}", settings.rate_limit_auth_per_minute, 60)
    check_lockout(db, body.email)
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        record_login_result(db, body.email, success=False)
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "Account disabled")
    record_login_result(db, body.email, success=True)
    create_session(db, user, response)
    audit(db, user.id, "user.login", "user", user.id, ip=client_ip(request))
    return _user_out(db, user)


@router.post("/change-password")
def change_password(body: PasswordChangeIn, request: Request, response: Response,
                    user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    revoke_all_sessions(db, user)          # invalidate every other session
    create_session(db, user, response)     # keep this one logged in
    audit(db, user.id, "user.change_password", "user", user.id, ip=client_ip(request))
    return {"ok": True}


@router.post("/logout-all")
def logout_all(request: Request, response: Response,
               user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    revoke_all_sessions(db, user)
    destroy_session(db, request, response)
    audit(db, user.id, "user.logout_all", "user", user.id)
    return {"ok": True}


@router.post("/forgot-password")
def forgot_password(body: ForgotIn, request: Request, db: DBSession = Depends(get_db)):
    """Always returns ok (no account enumeration). Token is e-mailed via the
    configured backend (console in dev)."""
    rate_limit(f"forgot:{client_ip(request)}", 5, 3600)
    user = db.query(User).filter(User.email == body.email.lower(),
                                 User.is_active == True).first()  # noqa: E712
    if user:
        token = secrets.token_urlsafe(32)
        db.add(PasswordReset(token=token, user_id=user.id,
                             expires_at=datetime.now(timezone.utc) + timedelta(hours=2)))
        db.commit()
        from ..notify import notify
        notify(db, user, "password_reset", "Password reset requested",
               f"Use this token to reset your CivicLens password (valid 2 hours): {token}")
        audit(db, user.id, "user.forgot_password", "user", user.id, ip=client_ip(request))
    return {"ok": True}


@router.post("/reset-password")
def reset_password(body: ResetIn, request: Request, db: DBSession = Depends(get_db)):
    rate_limit(f"reset:{client_ip(request)}", 10, 3600)
    pr = db.get(PasswordReset, body.token)
    if not pr or pr.used:
        raise HTTPException(400, "Invalid or already-used reset token")
    exp = pr.expires_at if pr.expires_at.tzinfo else pr.expires_at.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(400, "Reset token expired")
    user = db.get(User, pr.user_id)
    if not user:
        raise HTTPException(400, "Invalid token")
    user.password_hash = hash_password(body.new_password)
    pr.used = True
    db.commit()
    revoke_all_sessions(db, user)
    audit(db, user.id, "user.reset_password", "user", user.id, ip=client_ip(request))
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: DBSession = Depends(get_db)):
    destroy_session(db, request, response)
    return {"ok": True}


@router.get("/me", response_model=UserOut | None)
def me(user=Depends(get_current_user), db: DBSession = Depends(get_db)):
    return _user_out(db, user) if user else None


@router.patch("/settings", response_model=UserOut)
def update_settings(body: SettingsIn, user: User = Depends(require_user),
                    db: DBSession = Depends(get_db)):
    for field in ("name", "language", "city", "email_notifications", "phone"):
        v = getattr(body, field)
        if v is not None:
            setattr(user, field, v)
    db.add(user)
    db.commit()
    return _user_out(db, user)


@router.delete("/me")
def delete_my_account(request: Request, response: Response,
                      user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    """Privacy: user-initiated account deletion. Reports are anonymised, not lost."""
    from ..models import Report
    db.query(Report).filter(Report.reporter_id == user.id).update({"reporter_id": None})
    audit(db, user.id, "user.delete_account", "user", user.id)
    destroy_session(db, request, response)
    user.is_active = False
    user.email = f"deleted-{user.id}@deleted.civiclens"
    user.name = "Deleted user"
    user.phone = None
    db.commit()
    return {"ok": True}
