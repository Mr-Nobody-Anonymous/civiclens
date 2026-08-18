"""City intelligence: reports -> clusters -> hotspots -> emerging trends.

Everything here is deterministic aggregation over real data, presented as
ADVISORY information. The output explicitly labels AI/statistical advisories;
authorities decide what to act on.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from .models import OPEN_STATUSES, IssueCluster, Report


def hotspots(db: DBSession, city: str | None = None, days: int = 30,
             grid: float = 0.01) -> list[dict]:
    """Grid-based hotspot detection (~1.1km cells) with week-over-week trend."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    q = db.query(Report).filter(Report.created_at >= since,
                                Report.latitude.isnot(None),
                                Report.is_flagged == False)  # noqa: E712
    if city:
        q = q.filter(Report.city == city)
    rows = q.all()

    cells: dict = defaultdict(lambda: {"count": 0, "recent": 0, "prior": 0,
                                       "categories": defaultdict(int),
                                       "reporters": set(), "max_sev": 0})
    half = now - timedelta(days=max(1, days // 2))
    for r in rows:
        key = (round(r.latitude / grid) * grid, round(r.longitude / grid) * grid)
        c = cells[key]
        c["count"] += 1
        c["categories"][r.category or "Other"] += 1
        if r.reporter_id:
            c["reporters"].add(r.reporter_id)
        c["max_sev"] = max(c["max_sev"], r.severity or 0)
        if r.created_at and (r.created_at.replace(tzinfo=timezone.utc)
                             if r.created_at.tzinfo is None else r.created_at) >= half:
            c["recent"] += 1
        else:
            c["prior"] += 1

    out = []
    for (lat, lng), c in cells.items():
        if c["count"] < 3:
            continue
        top_cat = max(c["categories"], key=c["categories"].get)
        trend = None
        if c["prior"] > 0:
            trend = round((c["recent"] - c["prior"]) / c["prior"] * 100)
        out.append({
            "lat": round(lat, 4), "lng": round(lng, 4), "count": c["count"],
            "top_category": top_cat, "max_severity": c["max_sev"],
            "unique_reporters": len(c["reporters"]),
            "trend_pct": trend,
            "advisory": (f"Unusual increase in {top_cat.lower()} reports in this area "
                         f"(+{trend}% vs the previous period)." if trend and trend >= 40
                         else None),
        })
    out.sort(key=lambda h: -h["count"])
    return out[:25]


def emerging_trends(db: DBSession, city: str | None = None) -> list[dict]:
    """Category-level week-over-week movement across the whole city."""
    now = datetime.now(timezone.utc)
    def count_between(cat, a, b):
        q = db.query(func.count(Report.id)).filter(
            Report.category == cat, Report.created_at >= a, Report.created_at < b,
            Report.is_flagged == False)  # noqa: E712
        if city:
            q = q.filter(Report.city == city)
        return q.scalar() or 0

    cats = [c[0] for c in db.query(Report.category).filter(
        Report.category.isnot(None)).distinct().all()]
    out = []
    for cat in cats:
        this_week = count_between(cat, now - timedelta(days=7), now)
        prev_week = count_between(cat, now - timedelta(days=14), now - timedelta(days=7))
        if this_week < 2:
            continue
        change = round((this_week - prev_week) / prev_week * 100) if prev_week else None
        out.append({
            "category": cat, "this_week": this_week, "prev_week": prev_week,
            "change_pct": change,
            "advisory": (f"{cat} reports increased {change}% this week — the area may "
                         "warrant attention." if change and change >= 50 else None),
        })
    out.sort(key=lambda t: -(t["change_pct"] or 0))
    return out


def city_overview(db: DBSession, city: str | None = None) -> dict:
    """The 'what is happening across the city' answer, all real data."""
    def base(q):
        return q.filter(Report.city == city) if city else q

    open_count = base(db.query(func.count(Report.id)).filter(
        Report.status.in_(OPEN_STATUSES))).scalar() or 0
    critical = base(db.query(func.count(Report.id)).filter(
        Report.status.in_(OPEN_STATUSES), Report.severity >= 5)).scalar() or 0
    clusters_q = db.query(func.count(IssueCluster.id)).filter(
        IssueCluster.status == "open", IssueCluster.report_count > 1)
    if city:
        clusters_q = clusters_q.filter(IssueCluster.city == city)
    return {
        "city": city or "all",
        "open_reports": open_count,
        "critical_open": critical,
        "active_clusters": clusters_q.scalar() or 0,
        "hotspots": hotspots(db, city)[:8],
        "emerging_trends": emerging_trends(db, city)[:8],
        "advisory_note": ("Statistical/AI advisories highlight patterns in citizen "
                          "reports. Authorities review and decide on all actions."),
    }
