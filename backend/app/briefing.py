"""Civic Briefing: the morning screen where the full pipeline converges.

Reports → evidence → AI classification → duplicates → clusters → hotspots →
trends → SLA → community verification → organization performance → briefing.

Every number is deterministic aggregation of real data. The advisory paragraph
is template-generated from those numbers (no LLM required, LLM-upgradable) and
is always labelled: "AI-generated advisory. Human decision required."
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from .models import (OPEN_STATUSES, CommunityVote, EscalationEvent,
                     IssueCluster, Report, ReportStatus)
from .intelligence import emerging_trends, hotspots


def civic_briefing(db: DBSession, city: str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    def base(q):
        q = q.filter(Report.is_flagged == False)  # noqa: E712
        return q.filter(Report.city == city) if city else q

    critical_open = base(db.query(func.count(Report.id)).filter(
        Report.status.in_(OPEN_STATUSES), Report.severity >= 4)).scalar() or 0
    new_week = base(db.query(func.count(Report.id)).filter(
        Report.created_at >= week_ago)).scalar() or 0

    sla_breaches = db.query(func.count(EscalationEvent.id)).filter(
        EscalationEvent.created_at >= week_ago).scalar() or 0

    reopened = base(db.query(func.count(Report.id)).filter(
        Report.status == ReportStatus.reopened)).scalar() or 0

    citizens_week = base(db.query(func.count(func.distinct(Report.reporter_id))).filter(
        Report.created_at >= week_ago, Report.reporter_id.isnot(None))).scalar() or 0

    disputes_week = base(db.query(func.count(Report.id)).filter(
        Report.resolution_confirmed == False)).scalar() or 0  # noqa: E712

    community_week = db.query(func.count(CommunityVote.id)).filter(
        CommunityVote.created_at >= week_ago).scalar() or 0

    hs = hotspots(db, city, days=30)
    trends = emerging_trends(db, city)
    top_hotspot = hs[0] if hs else None
    top_trend = trends[0] if trends and (trends[0].get("change_pct") or 0) > 0 else None

    big_clusters = (db.query(IssueCluster)
                    .filter(IssueCluster.status == "open", IssueCluster.report_count >= 3,
                            *([IssueCluster.city == city] if city else []))
                    .order_by(IssueCluster.report_count.desc()).limit(3).all())

    # -------- advisory paragraph: generated from the numbers, clearly labelled --------
    lines = []
    if top_trend and top_trend.get("change_pct") and top_trend["change_pct"] >= 30:
        lines.append(f"{top_trend['category']} reports increased "
                     f"{top_trend['change_pct']}% this week.")
    if top_hotspot:
        lines.append(f"The largest hotspot has {top_hotspot['count']} "
                     f"{top_hotspot['top_category'].lower()} reports around "
                     f"({top_hotspot['lat']}, {top_hotspot['lng']}).")
    if big_clusters:
        c = big_clusters[0]
        lines.append(f"{c.report_count} reports from {c.unique_reporters} citizens appear "
                     f"to describe the same underlying issue: \u201c{c.title[:70]}\u201d.")
    if sla_breaches:
        lines.append(f"{sla_breaches} SLA escalations were raised in the last 7 days — "
                     "reviewing the assigned organizations' queues is recommended.")
    if reopened:
        lines.append(f"{reopened} report(s) are currently reopened after disputed resolutions.")
    if not lines:
        lines.append("No unusual patterns detected this week.")

    return {
        "city": city or "all", "generated_at": now.isoformat(),
        "kpis": {
            "critical_emerging": critical_open,
            "new_reports_week": new_week,
            "sla_breaches_week": sla_breaches,
            "reopened_issues": reopened,
            "citizens_engaged_week": citizens_week,
            "community_votes_week": community_week,
            "disputed_resolutions": disputes_week,
        },
        "top_trend": top_trend,
        "top_hotspot": top_hotspot,
        "largest_clusters": [{
            "id": c.id, "title": c.title, "category": c.category,
            "report_count": c.report_count, "unique_reporters": c.unique_reporters,
        } for c in big_clusters],
        "advisory": " ".join(lines),
        "advisory_label": "AI-generated advisory. Human decision required.",
    }
