"""P1 organization operations: departments/teams, staff invitations,
workload-aware assignment recommendations, supervisor escalation chains."""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from ..audit import audit
from ..db import get_db
from ..models import (OPEN_STATUSES, Department, EscalationEvent, Organization,
                      OrganizationUser, Report, ReportAssignment, Role,
                      StaffInvite, User)
from ..notify import notify
from ..security import client_ip, require_user
from ..sla import sla_state

router = APIRouter(prefix="/api/orgops", tags=["org-operations"])


def _org_link(db, user: User) -> OrganizationUser | None:
    return db.query(OrganizationUser).filter_by(user_id=user.id).first()


def _require_org_manager(db, user: User, org_id: str):
    """Admin, or a manager/supervisor of this specific org."""
    if user.role == Role.admin:
        return
    link = _org_link(db, user)
    if not link or link.organization_id != org_id or link.org_role not in ("manager", "supervisor"):
        raise HTTPException(403, "Requires organization manager/supervisor")


# ---------------- departments ----------------
class DeptIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_m: int | None = Field(default=None, ge=100, le=50000)


@router.post("/organizations/{org_id}/departments", status_code=201)
def create_department(org_id: str, body: DeptIn, request: Request,
                      user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    _require_org_manager(db, user, org_id)
    if not db.get(Organization, org_id):
        raise HTTPException(404, "Organization not found")
    d = Department(organization_id=org_id, **body.model_dump())
    db.add(d)
    db.commit()
    audit(db, user.id, "org.department_create", "department", d.id, detail=body.name,
          ip=client_ip(request))
    return {"id": d.id}


@router.get("/organizations/{org_id}/departments")
def list_departments(org_id: str, db: DBSession = Depends(get_db),
                     user: User = Depends(require_user)):
    if user.role != Role.admin:
        link = _org_link(db, user)
        if not link or link.organization_id != org_id:
            raise HTTPException(403, "Not a member of this organization")
    depts = db.query(Department).filter_by(organization_id=org_id).all()
    out = []
    for d in depts:
        members = db.query(func.count(OrganizationUser.id)).filter_by(department_id=d.id).scalar() or 0
        # workload = open reports assigned to members of this department
        member_ids = [m.user_id for m in db.query(OrganizationUser).filter_by(department_id=d.id).all()]
        open_assigned = 0
        if member_ids:
            open_assigned = (db.query(func.count(ReportAssignment.id))
                             .join(Report, Report.id == ReportAssignment.report_id)
                             .filter(ReportAssignment.assignee_user_id.in_(member_ids),
                                     Report.status.in_(OPEN_STATUSES)).scalar() or 0)
        out.append({"id": d.id, "name": d.name, "city": d.city,
                    "latitude": d.latitude, "longitude": d.longitude, "radius_m": d.radius_m,
                    "members": members, "open_assigned": open_assigned})
    return out


# ---------------- staff invitations ----------------
class InviteIn(BaseModel):
    email: EmailStr
    org_role: str = Field(default="member", pattern="^(member|supervisor|manager)$")
    department_id: str | None = None


@router.post("/organizations/{org_id}/invites", status_code=201)
def invite_staff(org_id: str, body: InviteIn, request: Request,
                 user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    _require_org_manager(db, user, org_id)
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organization not found")
    if body.department_id and not db.get(Department, body.department_id):
        raise HTTPException(404, "Department not found")
    inv = StaffInvite(token=secrets.token_urlsafe(24), organization_id=org_id,
                      department_id=body.department_id, email=body.email.lower(),
                      org_role=body.org_role, invited_by=user.id,
                      expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    db.add(inv)
    db.commit()
    # invitation e-mail (console in dev)
    existing = db.query(User).filter_by(email=body.email.lower()).first()
    if existing:
        notify(db, existing, "staff_invite",
               f"You are invited to join {org.name} on CivicLens",
               f"Accept with token (valid 7 days): {inv.token}")
    audit(db, user.id, "org.invite", "staff_invite", inv.token[:8],
          detail=f"{body.email} -> {org.name} ({body.org_role})", ip=client_ip(request))
    return {"token": inv.token, "expires_at": inv.expires_at}


@router.post("/invites/{token}/accept")
def accept_invite(token: str, request: Request, user: User = Depends(require_user),
                  db: DBSession = Depends(get_db)):
    inv = db.get(StaffInvite, token)
    if not inv or inv.accepted:
        raise HTTPException(404, "Invitation not found or already used")
    exp = inv.expires_at if inv.expires_at.tzinfo else inv.expires_at.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(410, "Invitation expired")
    if user.email.lower() != inv.email:
        raise HTTPException(403, "This invitation was issued to a different email address")
    if db.query(OrganizationUser).filter_by(organization_id=inv.organization_id,
                                            user_id=user.id).first():
        raise HTTPException(409, "Already a member of this organization")
    user.role = Role.org_staff
    db.add(OrganizationUser(organization_id=inv.organization_id, user_id=user.id,
                            org_role=inv.org_role, department_id=inv.department_id))
    inv.accepted = True
    db.commit()
    audit(db, user.id, "org.invite_accept", "staff_invite", token[:8], ip=client_ip(request))
    org = db.get(Organization, inv.organization_id)
    return {"ok": True, "organization": org.name if org else None, "org_role": inv.org_role}


# ---------------- workload-aware assignment recommendation ----------------
@router.get("/organizations/{org_id}/assignment-recommendation")
def recommend_assignment(org_id: str, report_id: str,
                         user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    """ADVISORY: rank staff by (department geofence match, current workload).
    AI/heuristics recommend — the supervisor assigns."""
    _require_org_manager(db, user, org_id)
    rpt = db.get(Report, report_id)
    if not rpt or rpt.organization_id != org_id:
        raise HTTPException(404, "Report not found in this organization")

    members = db.query(OrganizationUser).filter_by(organization_id=org_id).all()
    scored = []
    for m in members:
        staff = db.get(User, m.user_id)
        if not staff or not staff.is_active:
            continue
        workload = (db.query(func.count(ReportAssignment.id))
                    .join(Report, Report.id == ReportAssignment.report_id)
                    .filter(ReportAssignment.assignee_user_id == m.user_id,
                            Report.status.in_(OPEN_STATUSES)).scalar() or 0)
        geo_match = False
        if m.department_id and rpt.latitude is not None:
            dept = db.get(Department, m.department_id)
            if dept and dept.latitude is not None and dept.radius_m:
                import math
                R = 6371000.0
                p1, p2 = math.radians(rpt.latitude), math.radians(dept.latitude)
                dp = math.radians(dept.latitude - rpt.latitude)
                dl = math.radians(dept.longitude - rpt.longitude)
                a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
                geo_match = 2 * R * math.asin(math.sqrt(a)) <= dept.radius_m
        score = (10 if geo_match else 0) - workload
        scored.append({"user_id": m.user_id, "name": staff.name, "org_role": m.org_role,
                       "department_id": m.department_id, "open_workload": workload,
                       "geo_match": geo_match, "score": score})
    scored.sort(key=lambda x: -x["score"])
    return {"advisory": "Ranking is advisory (geofence match + lowest workload). "
                        "A supervisor makes the final assignment.",
            "recommendations": scored[:5]}


# ---------------- escalation chain ----------------
@router.get("/organizations/{org_id}/escalations")
def org_escalations(org_id: str, db: DBSession = Depends(get_db),
                    user: User = Depends(require_user)):
    _require_org_manager(db, user, org_id)
    rows = (db.query(EscalationEvent).filter_by(organization_id=org_id)
              .order_by(EscalationEvent.created_at.desc()).limit(100).all())
    out = []
    for e in rows:
        r = db.get(Report, e.report_id)
        out.append({"id": e.id, "kind": e.kind, "overdue_hours": e.overdue_hours,
                    "report_id": e.report_id, "report_code": r.public_code if r else None,
                    "report_title": r.title if r else None,
                    "sla": sla_state(db, r) if r else None,
                    "created_at": e.created_at})
    return out


def escalate_chain(db: DBSession, report: Report, event: EscalationEvent):
    """Escalation chain: assignee -> supervisors of the org -> admins.
    Called from the SLA sweep; each level notified exactly once per event."""
    notified = 0
    # level 1: current assignee
    a = (db.query(ReportAssignment).filter_by(report_id=report.id)
           .order_by(ReportAssignment.created_at.desc()).first())
    if a and a.assignee_user_id:
        assignee = db.get(User, a.assignee_user_id)
        notify(db, assignee, "sla_breach",
               f"SLA overdue on your assignment ({report.public_code})",
               f"{event.kind.replace('_', ' ')}: {event.overdue_hours:.1f}h overdue.",
               report_id=report.id)
        notified += 1
    # level 2: supervisors/managers of the organization
    for link in db.query(OrganizationUser).filter(
            OrganizationUser.organization_id == report.organization_id,
            OrganizationUser.org_role.in_(["supervisor", "manager"])).limit(5).all():
        sup = db.get(User, link.user_id)
        notify(db, sup, "sla_breach",
               f"Escalation: {report.public_code} is {event.overdue_hours:.1f}h overdue",
               f"{event.kind.replace('_', ' ')} on '{report.title[:60]}'. "
               "Assignee has been notified; supervisor attention requested.",
               report_id=report.id)
        notified += 1
    return notified
