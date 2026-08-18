from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from ..audit import audit
from ..db import get_db
from ..models import (Organization, OrganizationRule, OrganizationUser, Role,
                      User, CATEGORIES)
from ..schemas import OrgCreate, OrgOut, RuleCreate
from ..security import require_admin, require_user

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.get("", response_model=list[OrgOut])
def list_orgs(db: DBSession = Depends(get_db)):
    return db.query(Organization).filter(Organization.is_active == True).order_by(Organization.name).all()  # noqa: E712


@router.post("", response_model=OrgOut, status_code=201)
def create_org(body: OrgCreate, user: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    if db.query(Organization).filter(Organization.name == body.name).first():
        raise HTTPException(409, "Organization already exists")
    org = Organization(**body.model_dump())
    db.add(org)
    db.commit()
    audit(db, user.id, "org.create", "organization", org.id, detail=org.name)
    return org


@router.post("/{org_id}/members", status_code=201)
def add_member(org_id: str, email: str, org_role: str = "member",
               user: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    org = db.get(Organization, org_id)
    member = db.query(User).filter(User.email == email.lower()).first()
    if not org or not member:
        raise HTTPException(404, "Organization or user not found")
    if db.query(OrganizationUser).filter_by(organization_id=org_id, user_id=member.id).first():
        raise HTTPException(409, "Already a member")
    member.role = Role.org_staff
    db.add(OrganizationUser(organization_id=org_id, user_id=member.id, org_role=org_role))
    db.commit()
    audit(db, user.id, "org.add_member", "organization", org_id, detail=email)
    return {"ok": True}


# ---------------- routing rules ----------------
rules_router = APIRouter(prefix="/api/rules", tags=["routing-rules"])


@rules_router.get("")
def list_rules(user: User = Depends(require_user), db: DBSession = Depends(get_db)):
    if user.role not in (Role.admin, Role.moderator):
        raise HTTPException(403, "Staff only")
    rules = db.query(OrganizationRule).order_by(OrganizationRule.category,
                                                OrganizationRule.priority).all()
    return [{
        "id": r.id, "category": r.category, "keywords": r.keywords, "city": r.city,
        "organization_id": r.organization_id,
        "organization_name": r.organization.name if r.organization else "?",
        "priority": r.priority, "auto_assign": r.auto_assign, "is_active": r.is_active,
    } for r in rules]


@rules_router.post("", status_code=201)
def create_rule(body: RuleCreate, user: User = Depends(require_admin),
                db: DBSession = Depends(get_db)):
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Unknown category")
    if not db.get(Organization, body.organization_id):
        raise HTTPException(404, "Organization not found")
    rule = OrganizationRule(**body.model_dump())
    db.add(rule)
    db.commit()
    audit(db, user.id, "rule.create", "organization_rule", rule.id)
    return {"id": rule.id}


@rules_router.delete("/{rule_id}")
def delete_rule(rule_id: str, user: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    r = db.get(OrganizationRule, rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    r.is_active = False
    db.commit()
    audit(db, user.id, "rule.deactivate", "organization_rule", rule_id)
    return {"ok": True}
