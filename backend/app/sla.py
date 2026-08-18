"""Organization SLA engine.

Policies (per organization, keyed by minimum severity) define acknowledge/
resolve windows. check_slas() runs periodically (worker loop + on-demand)
and creates EscalationEvents for breaches — notified once, never spammed.

Defaults (platform-wide, overridable per org via sla_policies rows):
  severity >= 5 (Critical): ack 1h,  resolve 24h
  severity >= 4 (Serious):  ack 4h,  resolve 72h
  severity >= 1 (Normal):   ack 24h, resolve 336h (14d)
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession

from .models import (OPEN_STATUSES, EscalationEvent, Organization, Report,
                     ReportStatus, SLAPolicy, User, Role)
from .notify import notify

log = logging.getLogger("civiclens.sla")

DEFAULTS = [  # (min_severity, ack_hours, resolve_hours)
    (5, 1, 24),
    (4, 4, 72),
    (1, 24, 336),
]


def policy_for(db: DBSession, org_id: str | None, severity: int | None) -> tuple[int, int]:
    """Return (ack_hours, resolve_hours) — org-specific row wins, else defaults."""
    sev = severity or 1
    if org_id:
        rows = (db.query(SLAPolicy).filter(SLAPolicy.organization_id == org_id)
                  .order_by(SLAPolicy.min_severity.desc()).all())
        for p in rows:
            if sev >= p.min_severity:
                return p.ack_hours, p.resolve_hours
    for min_sev, ack, res in DEFAULTS:
        if sev >= min_sev:
            return ack, res
    return DEFAULTS[-1][1], DEFAULTS[-1][2]


def _hours_since(ts) -> float:
    if ts is None:
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0


def sla_state(db: DBSession, r: Report) -> dict:
    """Current SLA status of one report (used by API serializers)."""
    if not r.organization_id or r.status not in OPEN_STATUSES:
        return {"tracked": False}
    ack_h, res_h = policy_for(db, r.organization_id, r.severity)
    age_h = _hours_since(r.created_at)
    acked = r.acknowledged_at is not None
    ack_overdue = (not acked) and age_h > ack_h
    res_overdue = age_h > res_h
    return {
        "tracked": True, "ack_hours": ack_h, "resolve_hours": res_h,
        "age_hours": round(age_h, 1), "acknowledged": acked,
        "ack_overdue_hours": round(age_h - ack_h, 1) if ack_overdue else 0,
        "resolve_overdue_hours": round(age_h - res_h, 1) if res_overdue else 0,
        "breached": ack_overdue or res_overdue,
    }


def check_slas(db: DBSession) -> int:
    """Scan open assigned reports; create + notify escalation events once per breach kind."""
    created = 0
    rows = (db.query(Report)
              .filter(Report.status.in_(OPEN_STATUSES),
                      Report.organization_id.isnot(None)).all())
    for r in rows:
        st = sla_state(db, r)
        if not st.get("breached"):
            continue
        for kind, overdue in (("ack_breach", st["ack_overdue_hours"]),
                              ("resolve_breach", st["resolve_overdue_hours"])):
            if overdue <= 0:
                continue
            exists = db.query(EscalationEvent).filter(
                EscalationEvent.report_id == r.id,
                EscalationEvent.kind == kind).first()
            if exists:
                continue
            ev = EscalationEvent(report_id=r.id, organization_id=r.organization_id,
                                 kind=kind, overdue_hours=overdue)
            db.add(ev)
            db.commit()
            created += 1
            try:
                from .metrics import inc as _minc
                _minc("civiclens_sla_escalations_total", {"kind": kind})
            except Exception:
                pass
            # notify admins once (escalation path: org didn't respond -> administrators)
            org = db.get(Organization, r.organization_id)
            for admin in db.query(User).filter(User.role == Role.admin,
                                               User.is_active == True).limit(5).all():  # noqa: E712
                notify(db, admin, "sla_breach",
                       f"SLA breach: {r.public_code} ({kind.replace('_', ' ')})",
                       f"{org.name if org else 'Organization'} is {overdue:.1f}h overdue on "
                       f"'{r.title[:60]}' (severity {r.severity or '?'}/5).",
                       report_id=r.id)
            # escalation chain: assignee -> supervisors -> (admins already above)
            try:
                from .routers.orgops import escalate_chain
                escalate_chain(db, r, ev)
            except Exception:
                log.exception("escalation chain failed (non-fatal)")
            ev.notified = True
            db.commit()
    return created


def org_sla_stats(db: DBSession, org_id: str) -> dict:
    open_rows = (db.query(Report)
                   .filter(Report.organization_id == org_id,
                           Report.status.in_(OPEN_STATUSES)).all())
    breached = [r for r in open_rows if sla_state(db, r).get("breached")]
    resolved = (db.query(Report)
                  .filter(Report.organization_id == org_id,
                          Report.status == ReportStatus.resolved,
                          Report.resolved_at.isnot(None)).all())
    ack_times = []
    for r in resolved + open_rows:
        if r.acknowledged_at and r.created_at:
            a, c = r.acknowledged_at, r.created_at
            if a.tzinfo is None: a = a.replace(tzinfo=timezone.utc)
            if c.tzinfo is None: c = c.replace(tzinfo=timezone.utc)
            ack_times.append((a - c).total_seconds() / 3600)
    total_tracked = len(open_rows) + len(resolved)
    compliant = total_tracked - len(breached)
    return {
        "open": len(open_rows), "overdue": len(breached),
        "critical_overdue": len([r for r in breached if (r.severity or 0) >= 5]),
        "avg_ack_hours": round(sum(ack_times) / len(ack_times), 1) if ack_times else None,
        "sla_compliance": round(compliant / total_tracked, 2) if total_tracked else None,
    }
