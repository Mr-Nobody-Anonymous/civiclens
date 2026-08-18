"""AI human-review system.

After every AI analysis we evaluate queueing signals — not just confidence:
  low_confidence   confidence < CL_AI_CONF_LOW... below high threshold
  high_severity    severity >= 4 always gets human eyes before auto-assign
  ai_disagreement  AI category != citizen-selected category
  integrity_flag   evidence integrity score below threshold

Queue entries feed the moderator "AI Review Queue"; every decision is stored
(AI prediction -> human correction) as a future training/eval dataset.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession

from .config import settings
from .models import AIReview, Report, ReportAIAnalysis

log = logging.getLogger("civiclens.review")

INTEGRITY_REVIEW_THRESHOLD = 0.6


def queue_reviews_for(db: DBSession, report: Report, ai: ReportAIAnalysis) -> list[AIReview]:
    """Create review entries for every triggered signal (idempotent per reason)."""
    entries = []
    existing = {r.reason for r in db.query(AIReview)
                .filter(AIReview.report_id == report.id,
                        AIReview.status == "pending").all()}

    def add(reason: str, detail: str):
        if reason in existing:
            return
        e = AIReview(report_id=report.id, analysis_id=ai.id if ai else None,
                     reason=reason, detail=detail)
        db.add(e)
        entries.append(e)

    conf = ai.confidence or 0 if ai else 0
    if ai and conf < settings.ai_conf_high:
        add("low_confidence",
            f"AI confidence {int(conf*100)}% is below the {int(settings.ai_conf_high*100)}% "
            "auto-confirmation threshold.")
    if ai and (ai.severity or 0) >= 4:
        add("high_severity",
            f"AI rated severity {ai.severity}/5 — high-impact classifications require human sign-off.")
    if ai and report.user_category and ai.category and report.user_category != ai.category:
        add("ai_disagreement",
            f"Reporter selected '{report.user_category}' but AI classified "
            f"'{ai.category}' ({int(conf*100)}% confidence).")
    if report.integrity_score is not None and report.integrity_score < INTEGRITY_REVIEW_THRESHOLD:
        add("integrity_flag",
            f"Evidence integrity score {int(report.integrity_score*100)}% — "
            "this report requires additional verification. "
            + (report.integrity_notes or ""))
    db.commit()
    return entries


def decide(db: DBSession, review: AIReview, reviewer_id: str, action: str,
           corrected_category: str | None = None, corrected_severity: int | None = None,
           reason: str = "") -> None:
    """Apply a human decision. 'accepted' keeps AI values; 'corrected' applies
    the human classification to the report; 'rejected' discards the AI
    recommendation (report stays in manual review)."""
    review.status = action
    review.reviewer_id = reviewer_id
    review.decided_at = datetime.now(timezone.utc)
    review.corrected_category = corrected_category
    review.corrected_severity = corrected_severity
    review.decision_reason = reason

    report = review.report
    if action == "corrected":
        if corrected_category:
            report.category = corrected_category
        if corrected_severity:
            report.severity = corrected_severity
        report.human_confirmed = True
        if review.analysis:
            review.analysis.corrected_by = reviewer_id
            review.analysis.corrected_at = datetime.now(timezone.utc)
    elif action == "accepted":
        report.human_confirmed = True
    # close sibling pending reviews for the same report — one decision resolves it
    for sibling in db.query(AIReview).filter(
            AIReview.report_id == report.id, AIReview.status == "pending",
            AIReview.id != review.id).all():
        sibling.status = action
        sibling.reviewer_id = reviewer_id
        sibling.decided_at = review.decided_at
        sibling.decision_reason = f"(resolved together with {review.reason})"
    db.commit()
