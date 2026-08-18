"""Resolution verification.

Rule enforced everywhere:
  AI recommends → deterministic backend validates → human can override → audit.

1. Evidence-required gate (deterministic): for physical-evidence categories an
   organization cannot mark a report resolved without resolution media, unless
   an admin/moderator overrides with a reason.
2. Advisory before/after comparison (AI-ish, but deterministic here): perceptual
   hashes of original vs resolution evidence produce an advisory score + text.
   It NEVER changes status by itself; low scores queue an AIReview entry.
3. Citizen confirmation: reporter can confirm ("fixed") or dispute ("still a
   problem" → reopen via the state machine).
"""
import logging

from sqlalchemy.orm import Session as DBSession

from .integrity import phash_distance
from .models import AIReview, Report

log = logging.getLogger("civiclens.resolution")

# categories where "resolved" requires photographic/video proof
EVIDENCE_REQUIRED_CATEGORIES = {
    "Roads & Transportation", "Garbage & Sanitation", "Water",
    "Electricity", "Public Buildings", "Safety",
}


def evidence_required(report: Report) -> bool:
    return (report.category or "") in EVIDENCE_REQUIRED_CATEGORIES


def has_resolution_evidence(report: Report) -> bool:
    return any(m.kind == "resolution" for m in report.media)


def advisory_comparison(db: DBSession, report: Report) -> tuple[float | None, str]:
    """Compare original vs resolution evidence (perceptual hashes).

    Interpretation is intentionally modest:
      - same scene, changed content (moderate distance)  -> consistent-looking fix
      - identical images (distance ~0)                   -> suspicious: nothing changed
      - completely unrelated (huge distance)             -> may not show the same place
    Output is ADVISORY ONLY and labelled as such.
    """
    originals = [m.phash for m in report.media if m.kind in ("video", "image") and m.phash]
    resolutions = [m.phash for m in report.media if m.kind == "resolution" and m.phash]
    if not originals or not resolutions:
        return None, ("Advisory: no comparable visual evidence on both sides — "
                      "human review recommended.")

    dmin = min(phash_distance(o, r) for o in originals for r in resolutions)
    if dmin <= 2:
        return 0.2, ("Advisory: resolution evidence is visually identical to the original "
                     "evidence — it may not show the issue as resolved. Human review recommended.")
    if dmin <= 26:
        return 0.85, ("Advisory: resolution evidence appears consistent with the reported "
                      "scene, with visible changes. A human reviewer may confirm.")
    return 0.5, ("Advisory: resolution evidence differs strongly from the original — it may "
                 "show a different location. Human review recommended.")


def run_resolution_check(db: DBSession, report: Report) -> None:
    """Store the advisory result; queue human review when score is low.
    Never changes report status — humans do that."""
    score, notes = advisory_comparison(db, report)
    report.resolution_check_score = score
    report.resolution_check_notes = notes
    db.commit()
    # queue human review when the advisory is low-confidence OR when there was
    # nothing comparable (score None) — "no evidence" is itself a review reason
    if score is None or score < 0.6:
        exists = db.query(AIReview).filter(
            AIReview.report_id == report.id,
            AIReview.reason == "resolution_check",
            AIReview.status == "pending").first()
        if not exists:
            db.add(AIReview(report_id=report.id, reason="resolution_check",
                            detail=notes))
            db.commit()
