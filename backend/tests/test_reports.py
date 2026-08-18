import io


def _make_report(client, **over):
    body = {
        "title": "Big pothole on main road",
        "description": "A deep dangerous pothole affecting many cars near the market.",
        "category": "Roads & Transportation", "city": "Addis Ababa",
        "latitude": 9.01, "longitude": 38.76,
        "captcha_a": 2, "captcha_b": 3, "captcha_answer": 5,
    }
    body.update(over)
    return client.post("/api/reports", json=body)


def test_create_report_anonymous_with_captcha(client):
    r = _make_report(client)
    assert r.status_code == 201
    data = r.json()
    assert data["public_code"].startswith("CL-")
    assert data["status"] == "submitted"


def test_captcha_required_for_anonymous(client):
    r = _make_report(client, captcha_answer=999)
    assert r.status_code == 400


def test_list_and_filter(client):
    r = client.get("/api/reports?category=Roads %26 Transportation")
    assert r.status_code == 200
    r = client.get("/api/reports?status=submitted")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_public_serialization_hides_reporter(citizen_client):
    r = _make_report(citizen_client)
    rid = r.json()["id"]
    citizen_client.post("/api/auth/logout")
    pub = citizen_client.get(f"/api/reports/{rid}").json()
    assert "reporter_email" not in pub and "reporter_name" not in pub


def test_media_type_validation(client):
    r = _make_report(client)
    rid = r.json()["id"]
    # exe disguised as video: magic bytes don't match
    fake = io.BytesIO(b"MZ\x90\x00" + b"0" * 100)
    resp = client.post(f"/api/reports/{rid}/media",
                       files={"file": ("evil.mp4", fake, "video/mp4")})
    assert resp.status_code == 415
    # totally wrong content type
    resp = client.post(f"/api/reports/{rid}/media",
                       files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")})
    assert resp.status_code == 415


def test_status_change_requires_staff(client):
    r = _make_report(client)
    rid = r.json()["id"]
    resp = client.patch(f"/api/reports/{rid}/status", json={"status": "resolved"})
    assert resp.status_code == 401


def test_admin_can_correct_ai_and_change_status(admin_client):
    r = _make_report(admin_client)
    rid = r.json()["id"]
    resp = admin_client.patch(f"/api/reports/{rid}/correction",
                              json={"severity": 5, "category": "Safety"})
    assert resp.status_code == 200
    resp = admin_client.patch(f"/api/reports/{rid}/status",
                              json={"status": "under_review", "note": "checking"})
    assert resp.status_code == 200
    detail = admin_client.get(f"/api/reports/{rid}").json()
    assert detail["severity"] == 5
    assert detail["category"] == "Safety"
    assert detail["status"] == "under_review"


def test_flagged_report_hidden_from_public(admin_client):
    r = _make_report(admin_client)
    rid = r.json()["id"]
    admin_client.post(f"/api/reports/{rid}/flag", json={"reason": "spam test"})
    admin_client.post("/api/auth/logout")
    assert admin_client.get(f"/api/reports/{rid}").status_code == 404
    ids = [x["id"] for x in admin_client.get("/api/reports?page_size=100").json()["items"]]
    assert rid not in ids
