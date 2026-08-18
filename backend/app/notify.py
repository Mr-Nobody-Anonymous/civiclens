"""Notification service: in-app records always; e-mail via pluggable channels.

Channels implement send(user, title, body). Console channel is the dev
fallback; SMTP for production; SMS/Telegram can be added by registering
new channel classes — nothing else changes.
"""
import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session as DBSession

from .config import settings
from .models import Notification, User

log = logging.getLogger("civiclens.notify")


class ConsoleEmail:
    def send(self, user: User, title: str, body: str):
        log.info("[EMAIL->%s] %s | %s", user.email, title, body)


class SmtpEmail:
    def send(self, user: User, title: str, body: str):
        msg = EmailMessage()
        msg["Subject"] = f"[CivicLens] {title}"
        msg["From"] = f"{settings.email_from_name} <{settings.email_from}>"
        msg["To"] = user.email
        greeting = ("ሰላም" if user.language == "am" else "Hello") + f" {user.name.split(' ')[0]},"
        footer = ("\n\n— CivicLens Ethiopia\n"
                  + ("ይህን ኢሜይል በማስተካከያ ገጽ ማጥፋት ይችላሉ።" if user.language == "am"
                     else "You can turn off these emails in Settings."))
        msg.set_content(f"{greeting}\n\n{body or title}{footer}")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            if settings.smtp_tls:
                s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)


def _email_channel():
    return SmtpEmail() if settings.email_backend == "smtp" else ConsoleEmail()


PREF_KIND_MAP = {   # notification kind -> preference toggle
    "assigned": "status_changes", "in_progress": "organization_response",
    "resolved": "resolution", "rejected": "status_changes",
    "reopened": "reopened", "followed_update": "followed_updates",
    "analyzed": "status_changes", "duplicate": "status_changes",
}


def notify(db: DBSession, user: User | None, kind: str, title: str, body: str = "",
           report_id: str | None = None):
    """Create in-app notification + real-time SSE push + best-effort e-mail.
    Respects the user's per-kind notification preferences."""
    if not user:
        return
    pref_key = PREF_KIND_MAP.get(kind)
    if pref_key:
        import json as _json
        try:
            prefs = _json.loads(user.notif_prefs or "{}")
        except Exception:
            prefs = {}
        if prefs.get(pref_key) is False:
            return   # user opted out of this kind
    db.add(Notification(user_id=user.id, report_id=report_id, kind=kind,
                        title=title, body=body, channel="inapp"))
    db.commit()
    try:  # real-time push (SSE); never fatal
        from .events import publish
        publish(user.id, {"kind": kind, "title": title, "body": body, "report_id": report_id})
    except Exception:
        log.debug("SSE publish skipped")
    try:  # web push (best-effort bonus channel; no-op unless VAPID configured)
        from .push import send_push
        send_push(db, user, title, body, report_id=report_id)
    except Exception:
        log.debug("web push skipped")
    if user.email_notifications:
        from .circuit import smtp_breaker, CircuitOpen
        for attempt in range(2):  # one retry for transient SMTP failures
            try:
                smtp_breaker.call(_email_channel().send, user, title, body)
                break
            except CircuitOpen:
                log.warning("SMTP circuit open — email skipped (in-app + SSE delivered)")
                break
            except Exception as e:  # never break the request because SMTP failed
                log.warning("email send failed (attempt %d): %s", attempt + 1, e)
