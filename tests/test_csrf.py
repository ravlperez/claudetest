"""
Acceptance criteria for TASK 6:
- Valid SSR form submits with a correct CSRF token succeed.
- Missing CSRF token on any SSR POST → 403.
- Invalid / tampered CSRF token on any SSR POST → 403.

API routes (/api/*) are exempt from CSRF (JSON-body endpoints).
"""

from src.app.csrf import generate_csrf_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER = {"email": "user@example.com", "password": "password123", "role": "learner"}


def _create_user_via_api(client):
    """Create a user via the JSON API (no CSRF needed there)."""
    client.post("/api/auth/signup", json=_USER)
    client.cookies.clear()


# ---------------------------------------------------------------------------
# /signup form CSRF
# ---------------------------------------------------------------------------


def test_signup_form_with_valid_csrf_succeeds(client):
    """POST /signup with a valid CSRF token must redirect (303) to /."""
    r = client.post(
        "/signup",
        data={
            "email": "newuser@example.com",
            "password": "password123",
            "role": "learner",
            "csrf_token": generate_csrf_token(),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_signup_form_without_csrf_returns_403(client):
    r = client.post(
        "/signup",
        data={"email": "newuser@example.com", "password": "password123", "role": "learner"},
    )
    assert r.status_code == 403


def test_signup_form_with_empty_csrf_returns_403(client):
    r = client.post(
        "/signup",
        data={
            "email": "newuser@example.com",
            "password": "password123",
            "role": "learner",
            "csrf_token": "",
        },
    )
    assert r.status_code == 403


def test_signup_form_with_tampered_csrf_returns_403(client):
    r = client.post(
        "/signup",
        data={
            "email": "newuser@example.com",
            "password": "password123",
            "role": "learner",
            "csrf_token": "tampered.invalid.signature.value",
        },
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# /login form CSRF
# ---------------------------------------------------------------------------


def test_login_form_with_valid_csrf_succeeds(client):
    """POST /login with valid CSRF + correct credentials must redirect (303)."""
    _create_user_via_api(client)
    r = client.post(
        "/login",
        data={
            "email": _USER["email"],
            "password": _USER["password"],
            "csrf_token": generate_csrf_token(),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_login_form_without_csrf_returns_403(client):
    _create_user_via_api(client)
    r = client.post(
        "/login",
        data={"email": _USER["email"], "password": _USER["password"]},
    )
    assert r.status_code == 403


def test_login_form_with_tampered_csrf_returns_403(client):
    _create_user_via_api(client)
    r = client.post(
        "/login",
        data={
            "email": _USER["email"],
            "password": _USER["password"],
            "csrf_token": "not.a.real.token",
        },
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# /logout CSRF
# ---------------------------------------------------------------------------


def test_logout_with_valid_csrf_succeeds(client):
    """POST /logout with valid CSRF token must redirect (303) to /login."""
    client.post("/api/auth/signup", json=_USER)  # log in via API
    r = client.post(
        "/logout",
        data={"csrf_token": generate_csrf_token()},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_logout_without_csrf_returns_403(client):
    client.post("/api/auth/signup", json=_USER)
    r = client.post("/logout", follow_redirects=False)
    assert r.status_code == 403


def test_logout_with_tampered_csrf_returns_403(client):
    client.post("/api/auth/signup", json=_USER)
    r = client.post(
        "/logout",
        data={"csrf_token": "tampered"},
        follow_redirects=False,
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET pages still return a CSRF token in rendered HTML
# ---------------------------------------------------------------------------


def test_signup_page_contains_csrf_field(client):
    r = client.get("/signup")
    assert r.status_code == 200
    assert b'name="csrf_token"' in r.content


def test_login_page_contains_csrf_field(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b'name="csrf_token"' in r.content
