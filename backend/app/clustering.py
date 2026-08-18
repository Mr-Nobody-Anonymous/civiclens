"""Issue clustering: many reports -> one underlying civic issue.

A new report joins an existing OPEN cluster when it is:
  same category AND within CL_CLUSTER_RADIUS_M AND cluster still open.
Otherwise it seeds a new cluster. Reports are only ever *associated* —
nothing is merged or deleted, and every report keeps its own lifecycle.
"""
import math

from sqlalchemy.orm import Session as DBSession

from .models import IssueCluster, Report

CLUSTER_RADIUS_M = 300.0


def _haversine_m(lat1, lng1, lat2, lng2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def assign_cluster(db: DBSession, report: Report) -> IssueCluster | None:
    if report.latitude is None or not report.category:
        return None

    candidates = (db.query(IssueCluster)
                    .filter(IssueCluster.status == "open",
                            IssueCluster.category == report.category,
                            IssueCluster.latitude.between(report.latitude - 0.02, report.latitude + 0.02),
                            IssueCluster.longitude.between(report.longitude - 0.02, report.longitude + 0.02))
                    .all())
    best, best_d = None, CLUSTER_RADIUS_M + 1
    for c in candidates:
        d = _haversine_m(report.latitude, report.longitude, c.latitude, c.longitude)
        if d <= CLUSTER_RADIUS_M and d < best_d:
            best, best_d = c, d

    if best:
        report.cluster_id = best.id
        _recount(db, best)
    else:
        best = IssueCluster(
            title=report.title[:200], category=report.category, city=report.city,
            latitude=report.latitude, longitude=report.longitude,
            severity=report.severity, report_count=1, unique_reporters=1,
            first_reported=report.created_at, last_reported=report.created_at)
        db.add(best)
        db.flush()
        report.cluster_id = best.id
    db.commit()
    return best


def _recount(db: DBSession, cluster: IssueCluster):
    rows = db.query(Report).filter(Report.cluster_id == cluster.id).all()
    rows_plus = rows  # the joining report is committed by caller afterwards; recount is re-run cheaply
    cluster.report_count = len(rows_plus) + 1
    cluster.unique_reporters = len({r.reporter_id for r in rows_plus if r.reporter_id}) or 1
    cluster.severity = max([r.severity or 0 for r in rows_plus] + [cluster.severity or 0]) or None
    lasts = [r.created_at for r in rows_plus if r.created_at]
    if lasts:
        cluster.last_reported = max(lasts)


def refresh_cluster(db: DBSession, cluster_id: str):
    c = db.get(IssueCluster, cluster_id)
    if not c:
        return
    rows = db.query(Report).filter(Report.cluster_id == cluster_id).all()
    if not rows:
        return
    c.report_count = len(rows)
    c.unique_reporters = len({r.reporter_id for r in rows if r.reporter_id}) or 1
    c.severity = max((r.severity or 0) for r in rows) or None
    c.first_reported = min(r.created_at for r in rows)
    c.last_reported = max(r.created_at for r in rows)
    open_left = [r for r in rows if r.status.value not in ("resolved", "rejected", "duplicate")]
    c.status = "open" if open_left else "resolved"
    db.commit()
