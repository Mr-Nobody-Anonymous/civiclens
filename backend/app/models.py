"""SQLAlchemy models for CivicLens Ethiopia."""
import enum
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base


def now():
    return datetime.now(timezone.utc)


def gen_uuid():
    return uuid.uuid4().hex


def gen_public_code():
    # Human-friendly report code e.g. CL-4F7K2M
    return "CL-" + secrets.token_hex(3).upper()


class Role(str, enum.Enum):
    citizen = "citizen"
    moderator = "moderator"
    org_staff = "org_staff"
    admin = "admin"


class ReportStatus(str, enum.Enum):
    submitted = "submitted"
    ai_analysis = "ai_analysis"
    under_review = "under_review"      # includes needs_manual_routing (see routing_state)
    assigned = "assigned"
    in_progress = "in_progress"
    resolved = "resolved"
    rejected = "rejected"
    duplicate = "duplicate"
    reopened = "reopened"


OPEN_STATUSES = [ReportStatus.submitted, ReportStatus.ai_analysis, ReportStatus.under_review,
                 ReportStatus.assigned, ReportStatus.in_progress, ReportStatus.reopened]

# Central state machine: allowed transitions (enforced by app.state_machine)
STATUS_TRANSITIONS: dict = {
    ReportStatus.submitted: {ReportStatus.ai_analysis, ReportStatus.under_review,
                             ReportStatus.rejected, ReportStatus.duplicate},
    ReportStatus.ai_analysis: {ReportStatus.under_review, ReportStatus.assigned,
                               ReportStatus.rejected, ReportStatus.duplicate},
    ReportStatus.under_review: {ReportStatus.assigned, ReportStatus.in_progress,
                                ReportStatus.rejected, ReportStatus.duplicate,
                                ReportStatus.resolved},
    ReportStatus.assigned: {ReportStatus.in_progress, ReportStatus.under_review,
                            ReportStatus.resolved, ReportStatus.rejected,
                            ReportStatus.duplicate},
    ReportStatus.in_progress: {ReportStatus.resolved, ReportStatus.under_review,
                               ReportStatus.assigned, ReportStatus.rejected},
    ReportStatus.resolved: {ReportStatus.reopened},
    ReportStatus.rejected: {ReportStatus.reopened, ReportStatus.under_review},
    ReportStatus.duplicate: {ReportStatus.under_review},
    ReportStatus.reopened: {ReportStatus.under_review, ReportStatus.assigned,
                            ReportStatus.in_progress, ReportStatus.resolved,
                            ReportStatus.rejected},
}

CATEGORIES = [
    "Roads & Transportation", "Garbage & Sanitation", "Water", "Electricity",
    "Telecom", "Education", "Public Buildings", "Safety", "Environment", "Other",
]


class User(Base):
    __tablename__ = "users"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(32))
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(Role), default=Role.citizen, nullable=False)
    language = Column(String(8), default="en")
    city = Column(String(64))
    email_notifications = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=now)

    org_links = relationship("OrganizationUser", back_populates="user")


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String(64), primary_key=True)          # random token
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    csrf_token = Column(String(64))                    # double-submit CSRF token
    created_at = Column(DateTime(timezone=True), default=now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    user = relationship("User")


class LoginAttempt(Base):
    """Per-email brute-force lockout tracking."""
    __tablename__ = "login_attempts"
    email = Column(String(255), primary_key=True)
    failures = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    token = Column(String(64), primary_key=True)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now)


class Job(Base):
    """Persistent background-job state: retries, backoff, dead-letter, admin retry."""
    __tablename__ = "jobs"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    name = Column(String(64), nullable=False)
    payload = Column(Text)                    # JSON kwargs
    status = Column(String(16), default="queued", index=True)  # queued|running|done|failed|dead
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    last_error = Column(Text)
    run_after = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=now)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))


class Organization(Base):
    __tablename__ = "organizations"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    name = Column(String(160), unique=True, nullable=False)
    name_am = Column(String(160))
    org_type = Column(String(80))            # e.g. Telecom, Roads/Public Works
    description = Column(Text)
    contact_email = Column(String(255))
    city = Column(String(64))                # blank = national
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=now)


class OrganizationUser(Base):
    __tablename__ = "organization_users"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    organization_id = Column(String(32), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    org_role = Column(String(32), default="member")  # member | manager
    created_at = Column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    user = relationship("User", back_populates="org_links")
    organization = relationship("Organization")


class OrganizationRule(Base):
    """Configurable routing: category (+optional keywords/city) -> organization."""
    __tablename__ = "organization_rules"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    category = Column(String(64), nullable=False, index=True)
    keywords = Column(Text)                   # comma separated, optional
    city = Column(String(64))                 # optional: city-specific routing
    organization_id = Column(String(32), ForeignKey("organizations.id"), nullable=False)
    priority = Column(Integer, default=100)   # lower wins
    auto_assign = Column(Boolean, default=False)  # if True skip human review
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=now)

    organization = relationship("Organization")


class Report(Base):
    __tablename__ = "reports"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    public_code = Column(String(16), unique=True, default=gen_public_code, index=True)
    reporter_id = Column(String(32), ForeignKey("users.id"), index=True)  # nullable: anonymous
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    comments = Column(Text)
    category = Column(String(64), index=True)          # effective (AI or corrected)
    user_category = Column(String(64))                 # what the citizen picked
    issue_type = Column(String(120))
    severity = Column(Integer, index=True)             # 1..5 effective
    status = Column(Enum(ReportStatus), default=ReportStatus.submitted, nullable=False, index=True)
    city = Column(String(64), index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    address = Column(String(255))
    organization_id = Column(String(32), ForeignKey("organizations.id"), index=True)
    routing_state = Column(String(32), default="unrouted", index=True)
    # unrouted | routed | needs_manual_routing | manual
    routed_rule_id = Column(String(32), ForeignKey("organization_rules.id"))
    processing_state = Column(String(32), default="none")
    # none | queued | processing | done | failed  (AI pipeline state, never loses reports)
    processing_error = Column(Text)
    human_confirmed = Column(Boolean, default=False)   # human confirmed/overrode classification
    duplicate_of_id = Column(String(32), ForeignKey("reports.id"))
    is_demo = Column(Boolean, default=False)
    is_flagged = Column(Boolean, default=False)
    flag_reason = Column(String(255))
    created_at = Column(DateTime(timezone=True), default=now, index=True)
    resolved_at = Column(DateTime(timezone=True))

    reporter = relationship("User", foreign_keys=[reporter_id])
    organization = relationship("Organization")
    media = relationship("ReportMedia", back_populates="report", cascade="all,delete")
    ai = relationship("ReportAIAnalysis", back_populates="report", uselist=False, cascade="all,delete")
    __table_args__ = (
        Index("ix_reports_geo", "latitude", "longitude"),
        Index("ix_reports_status_sev", "status", "severity"),
    )


class ReportMedia(Base):
    __tablename__ = "report_media"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    report_id = Column(String(32), ForeignKey("reports.id"), nullable=False, index=True)
    kind = Column(String(16), nullable=False)         # video | image | resolution
    storage_key = Column(String(255), nullable=False) # private key, never a public URL
    thumb_key = Column(String(255))
    content_type = Column(String(80))
    size_bytes = Column(Integer)
    duration_s = Column(Float)
    width = Column(Integer)
    height = Column(Integer)
    original_name = Column(String(255))
    uploaded_by = Column(String(32), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=now)

    report = relationship("Report", back_populates="media")


class ReportAIAnalysis(Base):
    __tablename__ = "report_ai_analysis"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    report_id = Column(String(32), ForeignKey("reports.id"), nullable=False, unique=True)
    category = Column(String(64))
    issue_type = Column(String(120))
    severity = Column(Integer)
    confidence = Column(Float)
    urgency = Column(String(16))
    responsible_organization = Column(String(160))
    organization_type = Column(String(80))
    reasoning = Column(Text)
    model_name = Column(String(120))
    model_version = Column(String(40))
    analyzer = Column(String(64))              # heuristic | ollama | ...
    input_kind = Column(String(64))            # text | text+frames | text+images
    duration_ms = Column(Integer)
    success = Column(Boolean, default=True)
    frames_analyzed = Column(Integer, default=0)
    raw_json = Column(Text)
    corrected_by = Column(String(32), ForeignKey("users.id"))  # admin who overrode
    corrected_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=now)

    report = relationship("Report", back_populates="ai")


class ReportStatusHistory(Base):
    __tablename__ = "report_status_history"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    report_id = Column(String(32), ForeignKey("reports.id"), nullable=False, index=True)
    from_status = Column(String(32))
    to_status = Column(String(32), nullable=False)
    changed_by = Column(String(32), ForeignKey("users.id"))
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), default=now)


class ReportAssignment(Base):
    __tablename__ = "report_assignments"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    report_id = Column(String(32), ForeignKey("reports.id"), nullable=False, index=True)
    organization_id = Column(String(32), ForeignKey("organizations.id"), index=True)
    assignee_user_id = Column(String(32), ForeignKey("users.id"))   # internal assignee
    assigned_by = Column(String(32), ForeignKey("users.id"))
    source = Column(String(16), default="manual")   # ai | rule | manual
    accepted = Column(Boolean)
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), default=now)


class ReportComment(Base):
    __tablename__ = "report_comments"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    report_id = Column(String(32), ForeignKey("reports.id"), nullable=False, index=True)
    user_id = Column(String(32), ForeignKey("users.id"))
    body = Column(Text, nullable=False)
    internal = Column(Boolean, default=False)   # internal notes hidden from public
    created_at = Column(DateTime(timezone=True), default=now)
    user = relationship("User")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    report_id = Column(String(32), ForeignKey("reports.id"))
    kind = Column(String(40), nullable=False)   # received|analyzed|assigned|in_progress|resolved...
    title = Column(String(200), nullable=False)
    body = Column(Text)
    channel = Column(String(16), default="inapp")   # inapp | email (extensible: sms, telegram)
    read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String(32), primary_key=True, default=gen_uuid)
    user_id = Column(String(32), ForeignKey("users.id"))
    action = Column(String(80), nullable=False, index=True)
    entity = Column(String(40))
    entity_id = Column(String(40))
    detail = Column(Text)
    ip = Column(String(64))
    created_at = Column(DateTime(timezone=True), default=now, index=True)
