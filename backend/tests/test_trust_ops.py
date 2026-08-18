"""CivicLens 2.0 tests: AI review queue, evidence integrity, clustering, SLA."""
import io
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import (AIReview, EscalationEvent, IssueCluster, Report,
                        ReportAIAnalysis, ReportStatus)


def _mk_report(client, title="Trust test report", lat=9.01, lng=38.76, cat="Water", **over):
    body = {"title": title, "description": "A sufficiently long description of the issue here.",
            "category": cat, "city": "Addis Ababa", "latitude": lat, "longitude": lng,
            "captcha_a": 1, "captcha_b": 1, "captcha_answer": 2}
    body.update(over)
    return client.post("/api/reports", json=body).json()


# ---------------- AI review queue ----------------
def test_low_confidence_queues_review(client, admin_client):
    db = SessionLocal()
    r = _mk_report(client, title="Low conf review test")
    rpt = db.get(Report, r["id"])
    ai = ReportAIAnalysis(report_id=rpt.id, category="Water", issue_type="Leak",
                          severity=2, confidence=0.45, success=True)
    db.add(ai); db.commit()
    from app.review import queue_reviews_for
    entries = queue_reviews_for(db, rpt, ai)
    reasons = {e.reason for e in entries}
    assert "low_confidence" in reasons
    db.close()

    q = admin_client.get("/api/reviews").json()
    assert q["counts"]["total"] >= 1
    assert any(i["report"]["id"] == r["id"] for i in q["items"])


def test_high_severity_and_disagreement_queue(client):
    db = SessionLocal()
    r = _mk_report(client, title="Severity disagreement test", cat="Water")
    rpt = db.get(Report, r["id"])
    ai = ReportAIAnalysis(report_id=rpt.id, category="Roads & Transportation",
                          issue_type="Pothole", severity=5, confidence=0.9, success=True)
    db.add(ai); db.commit()
    from app.review import queue_reviews_for
    reasons = {e.reason for e in queue_reviews_for(db, rpt, ai)}
    assert "high_severity" in reasons
    assert "ai_disagreement" in reasons   # citizen said Water, AI said Roads
    db.close()


def test_review_decision_correction_applies_and_is_recorded(client, admin_client):
    db = SessionLocal()
    r = _mk_report(client, title="Correction flow test")
    rpt = db.get(Report, r["id"])
    ai = ReportAIAnalysis(report_id=rpt.id, category="Water", issue_type="Leak",
                          severity=2, confidence=0.5, success=True)
    db.add(ai); db.commit()
    from app.review import queue_reviews_for
    entry = queue_reviews_for(db, rpt, ai)[0]
    eid = entry.id
    db.close()

    resp = admin_client.post(f"/api/reviews/{eid}/decide", json={
        "action": "corrected", "corrected_category": "Safety",
        "corrected_severity": 4, "reason": "Open manhole, not a leak"})
    assert resp.status_code == 200

    db = SessionLocal()
    rpt = db.get(Report, r["id"])
    assert rpt.category == "Safety" and rpt.severity == 4
    assert rpt.human_confirmed is True
    rv = db.get(AIReview, eid)
    assert rv.status == "corrected" and rv.decision_reason.startswith("Open manhole")
    db.close()
    # history endpoint exposes the AI->human dataset
    hist = admin_client.get("/api/reviews/history").json()
    assert any(h["corrected_category"] == "Safety" for h in hist)


def test_review_double_decide_rejected(admin_client, client):
    db = SessionLocal()
    r = _mk_report(client, title="Double decide test")
    rpt = db.get(Report, r["id"])
    ai = ReportAIAnalysis(report_id=rpt.id, category="Water", severity=2,
                          confidence=0.4, success=True)
    db.add(ai); db.commit()
    from app.review import queue_reviews_for
    eid = queue_reviews_for(db, rpt, ai)[0].id
    db.close()
    assert admin_client.post(f"/api/reviews/{eid}/decide", json={"action": "accepted"}).status_code == 200
    assert admin_client.post(f"/api/reviews/{eid}/decide", json={"action": "rejected"}).status_code == 409


def test_review_queue_staff_only(client, citizen_client):
    assert citizen_client.get("/api/reviews").status_code == 403


# ---------------- evidence integrity ----------------
def test_identical_evidence_lowers_integrity(client):
    r1 = _mk_report(client, title="Original evidence report")
    r2 = _mk_report(client, title="Copied evidence report")
    payload = b"\x89PNG\r\n\x1a\n" + b"same-bytes" * 50
    for rid in (r1["id"], r2["id"]):
        resp = client.post(f"/api/reports/{rid}/media",
                           files={"file": ("ev.png", io.BytesIO(payload), "image/png")})
        assert resp.status_code == 201
    db = SessionLocal()
    from app.integrity import evaluate_report
    rpt2 = db.get(Report, r2["id"])
    score, notes = evaluate_report(db, rpt2)
    assert score < 0.9
    assert any("identical" in n for n in notes)
    db.close()


def test_location_mismatch_lowers_integrity(client):
    # claims Addis Ababa but pinned ~550km away (Mekelle coordinates)
    r = _mk_report(client, title="Location mismatch test", lat=13.4967, lng=39.4697)
    db = SessionLocal()
    from app.integrity import evaluate_report
    score, notes = evaluate_report(db, db.get(Report, r["id"]))
    assert score < 0.9
    assert any("km from" in n for n in notes)
    db.close()


def test_sha256_recorded_on_upload(client):
    r = _mk_report(client, title="Hash chain test")
    resp = client.post(f"/api/reports/{r['id']}/media",
                       files={"file": ("x.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"z" * 100), "image/png")})
    assert resp.status_code == 201
    db = SessionLocal()
    from app.models import ReportMedia
    m = db.query(ReportMedia).filter_by(report_id=r["id"]).first()
    assert m.sha256 and len(m.sha256) == 64
    db.close()


# ---------------- clustering ----------------
def test_nearby_same_category_reports_cluster(client):
    db = SessionLocal()
    from app.clustering import assign_cluster
    ids = []
    for i in range(3):
        r = _mk_report(client, title=f"Cluster pothole {i}",
                       lat=9.2000 + i * 0.0005, lng=38.9000, cat="Roads & Transportation")
        rpt = db.get(Report, r["id"])
        rpt.category = "Roads & Transportation"
        db.commit()
        assign_cluster(db, rpt)
        ids.append(r["id"])
    cluster_ids = {db.get(Report, i).cluster_id for i in ids}
    assert len(cluster_ids) == 1 and None not in cluster_ids
    c = db.get(IssueCluster, cluster_ids.pop())
    from app.clustering import refresh_cluster
    refresh_cluster(db, c.id)
    db.refresh(c)
    assert c.report_count == 3
    db.close()


def test_far_report_seeds_new_cluster(client):
    db = SessionLocal()
    from app.clustering import assign_cluster
    r1 = _mk_report(client, title="Cluster A", lat=9.5000, lng=38.9, cat="Water")
    r2 = _mk_report(client, title="Cluster B far away", lat=9.6000, lng=38.9, cat="Water")
    for rid in (r1["id"], r2["id"]):
        rpt = db.get(Report, rid)
        rpt.category = "Water"
        db.commit()
        assign_cluster(db, rpt)
    assert db.get(Report, r1["id"]).cluster_id != db.get(Report, r2["id"]).cluster_id
    db.close()


def test_cluster_api_public_detail(client, admin_client):
    rows = admin_client.get("/api/clusters").json()
    if rows:
        d = client.get(f"/api/clusters/{rows[0]['id']}").json()
        assert "reports" in d and d["report_count"] >= 1


# ---------------- SLA ----------------
def test_sla_policy_defaults():
    db = SessionLocal()
    from app.sla import policy_for
    assert policy_for(db, None, 5) == (1, 24)
    assert policy_for(db, None, 4) == (4, 72)
    assert policy_for(db, None, 2) == (24, 336)
    db.close()


def test_sla_breach_creates_escalation_once(client, admin_client):
    db = SessionLocal()
    from app.models import Organization
    org = db.query(Organization).first()
    r = _mk_report(client, title="SLA breach test report")
    rpt = db.get(Report, r["id"])
    rpt.organization_id = org.id
    rpt.severity = 5
    rpt.status = ReportStatus.assigned
    rpt.created_at = datetime.now(timezone.utc) - timedelta(hours=30)  # way past 1h ack + 24h resolve
    db.commit()

    from app.sla import check_slas, sla_state
    st = sla_state(db, rpt)
    assert st["breached"] and st["ack_overdue_hours"] > 0 and st["resolve_overdue_hours"] > 0

    n1 = check_slas(db)
    assert n1 >= 2   # ack + resolve breaches for this report
    n2 = check_slas(db)
    events = db.query(EscalationEvent).filter_by(report_id=rpt.id).count()
    assert events == 2   # idempotent — no duplicate escalations
    db.close()

    esc = admin_client.get("/api/sla/escalations").json()
    assert any(e["report_id"] == r["id"] for e in esc)


def test_acknowledge_stops_ack_clock(client, admin_client):
    db = SessionLocal()
    from app.models import Organization
    org = db.query(Organization).first()
    r = _mk_report(client, title="Ack clock test")
    rpt = db.get(Report, r["id"])
    rpt.organization_id = org.id
    rpt.severity = 5
    rpt.status = ReportStatus.assigned
    rpt.created_at = datetime.now(timezone.utc) - timedelta(hours=3)
    rpt.acknowledged_at = datetime.now(timezone.utc) - timedelta(hours=2, minutes=30)
    db.commit()
    from app.sla import sla_state
    st = sla_state(db, rpt)
    assert st["acknowledged"] is True
    assert st["ack_overdue_hours"] == 0   # acknowledged -> ack breach cleared
    db.close()
