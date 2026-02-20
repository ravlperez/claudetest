"""
Acceptance criteria for TASK 5:
- Signup creates a user (201)
- Login sets cookie and /api/me returns user (200)
- Logout clears cookie
- Wrong password returns 401
- Too many login attempts returns 429

All tests use an isolated in-memory SQLite database (see conftest.py).
"""

import pytest

from src.app.csrf import generate_csrf_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LEARNER = {"email": "learner@example.com", "password": "password123", "role": "learner"}
CREATOR = {"email": "creator@example.com", "password": "s3cur3pass", "role": "creator"}


def _signup(client, payload=None):
    payload = payload or LEARNER
    return client.post("/api/auth/signup", json=payload)


def _login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------


def test_signup_creates_user(client):
    r = _signup(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == LEARNER["email"]
    assert body["role"] == "learner"
    assert "id" in body


def test_signup_sets_session_cookie(client):
    r = _signup(client)
    assert r.status_code == 201
    assert "session" in r.cookies


def test_signup_duplicate_email_returns_409(client):
    _signup(client)
    r = _signup(client)  # second attempt with same email
    assert r.status_code == 409


def test_signup_short_password_returns_422(client):
    r = _signup(client, {"email": "x@example.com", "password": "short", "role": "learner"})
    assert r.status_code == 422


def test_signup_invalid_role_returns_422(client):
    r = _signup(client, {"email": "x@example.com", "password": "password123", "role": "admin"})
    assert r.status_code == 422


def test_signup_creator_role(client):
    r = _signup(client, CREATOR)
    assert r.status_code == 201
    assert r.json()["role"] == "creator"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_correct_credentials_returns_200(client):
    _signup(client)
    r = _login(client, LEARNER["email"], LEARNER["password"])
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == LEARNER["email"]
    assert body["role"] == "learner"


def test_login_sets_session_cookie(client):
    _signup(client)
    r = _login(client, LEARNER["email"], LEARNER["password"])
    assert r.status_code == 200
    assert "session" in r.cookies


def test_login_wrong_password_returns_401(client):
    _signup(client)
    r = _login(client, LEARNER["email"], "wrongpassword")
    assert r.status_code == 401


def test_login_unknown_email_returns_401(client):
    r = _login(client, "nobody@example.com", "password123")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# /api/me
# ---------------------------------------------------------------------------


def test_me_with_valid_session_returns_user(client):
    _signup(client)  # sets session cookie on the client jar
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["email"] == LEARNER["email"]


def test_me_without_session_returns_401(client):
    # Never log in
    r = client.get("/api/me")
    assert r.status_code == 401


def test_me_after_login_returns_user(client):
    _signup(client)
    client.cookies.clear()
    _login(client, LEARNER["email"], LEARNER["password"])
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json()["email"] == LEARNER["email"]


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


def test_logout_clears_cookie(client):
    _signup(client)
    assert client.get("/api/me").status_code == 200

    # POST /logout requires a CSRF token (form data)
    csrf = generate_csrf_token()
    r = client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 303

    # Cookie jar should no longer carry "session"
    client.cookies.clear()
    assert client.get("/api/me").status_code == 401


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_too_many_login_attempts_returns_429(client):
    """Six consecutive failed logins from the same IP must trigger 429."""
    _signup(client)
    for i in range(5):
        r = _login(client, LEARNER["email"], "badpassword")
        assert r.status_code == 401, f"attempt {i+1} should be 401"
    r = _login(client, LEARNER["email"], "badpassword")
    assert r.status_code == 429


# ---------------------------------------------------------------------------
# SSR pages (smoke)
# ---------------------------------------------------------------------------


def test_signup_page_renders(client):
    r = client.get("/signup")
    assert r.status_code == 200
    assert b"Sign Up" in r.content


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b"Log in" in r.content or b"Log In" in r.content
