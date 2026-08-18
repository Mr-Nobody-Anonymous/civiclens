from app.db import SessionLocal
from app.models import Organization, Report
from app.routing import route_report


def test_routing_matches_category(client):
    db = SessionLocal()
    try:
        rpt = Report(title="road broken", description="pothole everywhere",
                     category="Roads & Transportation", city="Addis Ababa")
        org, rule = route_report(db, rpt, "Roads & Transportation", "pothole on road")
        assert org is not None
        assert rule.category == "Roads & Transportation"
        # deterministic: the matched rule is the lowest-priority-number active rule
        # among those with equal keyword score
        from app.models import OrganizationRule
        best_prio = min(r.priority for r in db.query(OrganizationRule)
                        .filter_by(category="Roads & Transportation", is_active=True).all())
        assert rule.priority == best_prio
    finally:
        db.close()


def test_routing_no_rule_returns_none(client):
    db = SessionLocal()
    try:
        rpt = Report(title="x", description="y", category="Telecom")
        org, rule = route_report(db, rpt, "Telecom", "no network")
        assert org is None
    finally:
        db.close()


def test_dashboard_stats_requires_staff(client):
    assert client.get("/api/dashboard/stats").status_code == 401


def test_org_endpoints_require_membership(citizen_client):
    assert citizen_client.get("/api/dashboard/org-reports").status_code == 403
