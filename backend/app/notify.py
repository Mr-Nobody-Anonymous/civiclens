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


def notify(db: DBSession, user: User | None, kind: str, title: str, body: str = "",
           report_id: str | None = None):
    """Create in-app notification + best-effort e-mail."""
    if not user:
        return
    db.add(Notification(user_id=user.id, report_id=report_id, kind=kind,
                        title=title, body=body, channel="inapp"))
    db.commit()
    if user.email_notifications:
        for attempt in range(2):  # one retry for transient SMTP failures
            try:
                _email_channel().send(user, title, body)
                break
            except Exception as e:  # never break the request because SMTP failed
                log.warning("email send failed (attempt %d): %s", attempt + 1, e)
