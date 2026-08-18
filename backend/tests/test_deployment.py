"""Deployment-topology features: CSRF bootstrap endpoint, CORS origin config,
cookie SameSite derivation, ai_service_url scheme tolerance, entrypoint safety."""
import os
import subprocess

from app.config import Settings


# ---------------- /api/auth/csrf bootstrap (split-frontend support) ----------------

def test_csrf_bootstrap_anonymous_returns_null(client):
    r = client.get("/api/auth/csrf", cookies={})
    assert r.status_code == 200
    assert r.json() == {"csrf_token": None}


def test_csrf_bootstrap_returns_session_token(citizen_client):
    client = citizen_client
    r = client.get("/api/auth/csrf")
    assert r.status_code == 200
    token = r.json()["csrf_token"]
    assert token and isinstance(token, str) and len(token) > 20
    # the token it returns is the one that actually passes CSRF validation
    r2 = client.post("/api/auth/logout", headers={"X-CSRF-Token": token})
    assert r2.status_code == 200
    client.post("/api/auth/login", json={"email": "cit@test.et", "password": "citizen-pass-1"})


def test_csrf_bootstrap_bogus_cookie_returns_null(client):
    r = client.get("/api/auth/csrf", cookies={"cl_session": "not-a-real-session"})
    assert r.json() == {"csrf_token": None}


# ---------------- settings: CORS origins / SameSite derivation ----------------

def test_cors_origin_list_parsing():
    s = Settings(cors_origins="https://a.example.com, https://b.example.com/ ,")
    assert s.cors_origin_list == ["https://a.example.com", "https://b.example.com"]
    assert Settings(cors_origins="").cors_origin_list == []


def test_samesite_auto_none_when_cross_origin():
    s = Settings(cors_origins="https://app.example.com")
    assert s.effective_samesite == "none"
    # SameSite=None must force Secure even outside production
    assert s.cookie_secure is True


def test_samesite_defaults_lax_same_origin():
    s = Settings(cors_origins="")
    assert s.effective_samesite == "lax"


def test_samesite_explicit_override_wins():
    s = Settings(cors_origins="https://app.example.com", cookie_samesite="lax")
    assert s.effective_samesite == "lax"


def test_production_cookies_always_secure():
    assert Settings(env="production").cookie_secure is True
    assert Settings(env="development").cookie_secure is False


# ---------------- ai_service_url scheme tolerance (PaaS hostport vars) ----------------

def test_ai_url_adds_scheme_for_bare_hostport():
    assert Settings(ai_service_url="civiclens-ai:8090").ai_url == "http://civiclens-ai:8090"
    assert Settings(ai_service_url="http://ai:8090/").ai_url == "http://ai:8090"
    assert Settings(ai_service_url="https://ai.internal").ai_url == "https://ai.internal"


# ---------------- CORS middleware behavior ----------------

def test_cors_preflight_dev_wildcard(client):
    r = client.options("/api/reports", headers={
        "Origin": "https://anywhere.example",
        "Access-Control-Request-Method": "POST",
    })
    # dev mode: wildcard CORS active
    assert r.headers.get("access-control-allow-origin") in ("*", "https://anywhere.example")


# ---------------- docker-entrypoint.sh safety ----------------

ENTRYPOINT = os.path.join(os.path.dirname(__file__), "..", "docker-entrypoint.sh")


def test_entrypoint_exists_and_is_valid_shell():
    assert os.path.exists(ENTRYPOINT)
    out = subprocess.run(["sh", "-n", ENTRYPOINT], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_entrypoint_defaults_demo_data_off_in_production():
    src = open(ENTRYPOINT).read()
    assert 'CL_SEED_DEMO_DATA:-false' in src
    assert 'CL_CREATE_DEMO_ACCOUNTS:-false' in src
    # honors platform-injected $PORT
    assert '${PORT:-8000}' in src


def test_entrypoint_supports_all_roles():
    src = open(ENTRYPOINT).read()
    for role in ("api)", "worker)", "migrate)"):
        assert role in src
