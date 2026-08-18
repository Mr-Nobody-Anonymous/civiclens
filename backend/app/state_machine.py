"""Central report state-transition service.

Every status change in the platform MUST go through transition() so that:
 - invalid transitions are rejected (409)
 - history + audit entries are always written
 - resolved_at is maintained
 - reporter notifications fire exactly once per transition
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from .models import (Report, ReportStatus, ReportStatusHistory,
                     STATUS_TRANSITIONS, User)
from .notify import notify


NOTIFY_ON = {
    ReportStatus.assigned: ("assigned", "Your report was assigned to an organization",
                            "assigned_am", "ሪፖርትዎ ለተቋም ተመድቧል"),
    ReportStatus.in_progress: ("in_progress", "Work has started on your report",
                               "in_progress_am", "በሪፖርትዎ ላይ ሥራ ተጀምሯል"),
    ReportStatus.resolved: ("resolved", "Your report has been resolved",
                            "resolved_am", "ሪፖርትዎ ተፈትቷል"),
    ReportStatus.rejected: ("rejected", "Your report was reviewed and closed",
                            "rejected_am", "ሪፖርትዎ ተገምግሞ ተዘግቷል"),
    ReportStatus.reopened: ("reopened", "Your report was reopened",
                            "reopened_am", "ሪፖርትዎ እንደገና ተከፍቷል"),
}


def can_transition(from_s: ReportStatus, to_s: ReportStatus) -> bool:
    return to_s in STATUS_TRANSITIONS.get(from_s, set())


def transition(db: DBSession, report: Report, to_status: ReportStatus,
               actor: Optional[User] = None, note: str = "",
               force: bool = False) -> None:
    """Apply a status transition. Raises 409 on invalid transitions unless forced
    (force is reserved for system-internal pipeline moves)."""
    if report.status == to_status:
        return
    if not force and not can_transition(report.status, to_status):
        raise HTTPException(
            409, f"Invalid status transition: {report.status.value} → {to_status.value}")

    db.add(ReportStatusHistory(
        report_id=report.id, from_status=report.status.value,
        to_status=to_status.value, changed_by=actor.id if actor else None, note=note))
    report.status = to_status
    if to_status == ReportStatus.resolved:
        report.resolved_at = datetime.now(timezone.utc)
    db.commit()

    if report.reporter_id and to_status in NOTIFY_ON:
        kind, title_en, _k, title_am = NOTIFY_ON[to_status]
        reporter = db.get(User, report.reporter_id)
        title = title_am if (reporter and reporter.language == "am") else title_en
        notify(db, reporter, kind, f"{title} ({report.public_code})",
               note or "", report_id=report.id)
