import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["CL_DATABASE_URL"] = "sqlite:///" + tempfile.mktemp(suffix=".db")
os.environ["CL_STORAGE_DIR"] = tempfile.mkdtemp(prefix="cl_test_storage_")
os.environ["CL_RATE_LIMIT_REPORTS_PER_HOUR"] = "1000"
os.environ["CL_RATE_LIMIT_AUTH_PER_MINUTE"] = "1000"

import pytest
from fastapi.testclient import TestClient as _TestClient

from app.main import app


class TestClient(_TestClient):
    """TestClient that auto-attaches the CSRF header like the real frontend does."""
    def request(self, method, url, **kw):
        if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            csrf = self.cookies.get("cl_csrf")
            if csrf:
                headers = dict(kw.get("headers") or {})
                headers.setdefault("X-CSRF-Token", csrf)
                kw["headers"] = headers
        return super().request(method, url, **kw)
from app.db import Base, engine, SessionLocal
from app.models import Organization, OrganizationRule, Role, User
from app.security import hash_password


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    admin = User(name="Admin", email="admin@test.et", role=Role.admin,
                 password_hash=hash_password("admin-pass-123"))
    citizen = User(name="Citizen", email="cit@test.et", role=Role.citizen,
                   password_hash=hash_password("citizen-pass-1"))
    org = Organization(name="Test Roads Authority", org_type="Roads/Public Works")
    db.add_all([admin, citizen, org])
    db.commit()
    db.add(OrganizationRule(category="Roads & Transportation",
                            organization_id=org.id, priority=10))
    db.commit()
    db.close()
    return TestClient(app)


@pytest.fixture
def admin_client(client):
    client.post("/api/auth/login", json={"email": "admin@test.et", "password": "admin-pass-123"})
    yield client
    client.post("/api/auth/logout")


@pytest.fixture
def citizen_client(client):
    client.post("/api/auth/login", json={"email": "cit@test.et", "password": "citizen-pass-1"})
    yield client
    client.post("/api/auth/logout")
