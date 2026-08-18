def test_register_login_me(client):
    r = client.post("/api/auth/register", json={
        "name": "New User", "email": "new@test.et", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["role"] == "citizen"

    r = client.get("/api/auth/me")
    assert r.json()["email"] == "new@test.et"

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json() is None


def test_bad_password_rejected(client):
    r = client.post("/api/auth/login", json={"email": "admin@test.et", "password": "wrong"})
    assert r.status_code == 401


def test_duplicate_email_rejected(client):
    r = client.post("/api/auth/register", json={
        "name": "Dup", "email": "new@test.et", "password": "password123"})
    assert r.status_code == 409


def test_password_never_stored_plaintext():
    from app.security import hash_password, verify_password
    h = hash_password("secret-password")
    assert "secret-password" not in h
    assert h.startswith("pbkdf2$")
    assert verify_password("secret-password", h)
    assert not verify_password("other", h)
