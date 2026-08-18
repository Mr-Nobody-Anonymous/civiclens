"""Pydantic request/response schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# ---------- auth ----------
class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: Optional[str] = None
    language: str = "en"
    city: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    mfa_code: Optional[str] = None


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: str
    language: str
    city: Optional[str]
    email_notifications: bool
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None

    class Config:
        from_attributes = True


class SettingsIn(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    city: Optional[str] = None
    email_notifications: Optional[bool] = None
    phone: Optional[str] = None


# ---------- reports ----------
class ReportCreate(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    description: str = Field(min_length=10, max_length=5000)
    comments: Optional[str] = Field(default=None, max_length=2000)
    category: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    address: Optional[str] = Field(default=None, max_length=255)
    client_key: Optional[str] = Field(default=None, max_length=64)  # offline idempotency
    captcha_a: Optional[int] = None
    captcha_b: Optional[int] = None
    captcha_answer: Optional[int] = None


class MediaOut(BaseModel):
    id: str
    kind: str
    content_type: Optional[str]
    size_bytes: Optional[int]
    duration_s: Optional[float]
    has_thumb: bool
    created_at: datetime


class AIOut(BaseModel):
    category: Optional[str]
    issue_type: Optional[str]
    severity: Optional[int]
    confidence: Optional[float]
    urgency: Optional[str]
    responsible_organization: Optional[str]
    organization_type: Optional[str]
    reasoning: Optional[str]
    model_name: Optional[str]
    model_version: Optional[str]
    frames_analyzed: Optional[int]
    corrected: bool
    created_at: Optional[datetime]


class ReportPublic(BaseModel):
    """Public shape — NEVER include reporter personal info."""
    id: str
    public_code: str
    title: str
    description: str
    category: Optional[str]
    issue_type: Optional[str]
    severity: Optional[int]
    status: str
    city: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    address: Optional[str]
    organization_name: Optional[str]
    is_demo: bool
    created_at: datetime
    resolved_at: Optional[datetime]
    media: List[MediaOut] = []
    ai: Optional[AIOut] = None
    duplicate_of_code: Optional[str] = None
    possible_duplicate: bool = False


class ReportDetailPrivileged(ReportPublic):
    reporter_name: Optional[str] = None
    reporter_email: Optional[str] = None
    comments: Optional[str] = None
    is_flagged: bool = False
    flag_reason: Optional[str] = None
    user_category: Optional[str] = None


class StatusPatch(BaseModel):
    status: str
    note: Optional[str] = None


class AssignmentPatch(BaseModel):
    organization_id: Optional[str] = None
    assignee_user_id: Optional[str] = None
    note: Optional[str] = None
    accept: Optional[bool] = None


class CorrectionPatch(BaseModel):
    category: Optional[str] = None
    issue_type: Optional[str] = None
    severity: Optional[int] = Field(default=None, ge=1, le=5)
    note: Optional[str] = None


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)
    internal: bool = False


class FlagIn(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


# ---------- organizations ----------
class OrgOut(BaseModel):
    id: str
    name: str
    name_am: Optional[str]
    org_type: Optional[str]
    description: Optional[str]
    city: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


class OrgCreate(BaseModel):
    name: str
    name_am: Optional[str] = None
    org_type: Optional[str] = None
    description: Optional[str] = None
    contact_email: Optional[str] = None
    city: Optional[str] = None


class RuleOut(BaseModel):
    id: str
    category: str
    keywords: Optional[str]
    city: Optional[str]
    organization_id: str
    organization_name: str
    priority: int
    auto_assign: bool
    is_active: bool


class RuleCreate(BaseModel):
    category: str
    organization_id: str
    keywords: Optional[str] = None
    city: Optional[str] = None
    priority: int = 100
    auto_assign: bool = False
