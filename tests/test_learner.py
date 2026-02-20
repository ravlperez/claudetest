"""
Acceptance criteria for TASK 7:
- Learner can save profile (API + SSR form)
- Feed redirects to /onboarding when profile is missing
- Feed allows learner with a profile
- Creator cannot access learner profile endpoints (403)

All tests use an isolated in-memory SQLite database (see conftest.py).
"""

from src.app.csrf import generate_csrf_token

# ---------------------------------------------------------------------------
# Shared test users
# ---------------------------------------------------------------------------

_LEARNER = {"email": "learner@example.com", "password": "password123", "role": "learner"}
_CREATOR = {"email": "creator@example.com", "password": "s3cur3pass", "role": "creator"}
_PROFILE = {"target_language": "en", "level": "B1"}


def _signup(client, payload):
    """Sign up and leave the session cookie in the client jar."""
    client.post("/api/auth/signup", json=payload)


def _as_learner(client):
    _signup(client, _LEARNER)


def _as_creator(client):
    _signup(client, _CREATOR)


# ---------------------------------------------------------------------------
# API: POST /api/learner/profile
# ---------------------------------------------------------------------------


def test_learner_can_create_profile(client):
    _as_learner(client)
    r = client.post("/api/learner/profile", json=_PROFILE)
    assert r.status_code == 200
    body = r.json()
    assert body["target_language"] == "en"
    assert body["level"] == "B1"
    assert body["total_xp"] == 0


def test_learner_can_update_profile(client):
    _as_learner(client)
    client.post("/api/learner/profile", json=_PROFILE)
    r = client.post("/api/learner/profile", json={"target_language": "fr", "level": "A2"})
    assert r.status_code == 200
    assert r.json()["target_language"] == "fr"
    assert r.json()["level"] == "A2"


def test_invalid_language_returns_422(client):
    _as_learner(client)
    r = client.post("/api/learner/profile", json={"target_language": "de", "level": "B1"})
    assert r.status_code == 422


def test_invalid_level_returns_422(client):
    _as_learner(client)
    r = client.post("/api/learner/profile", json={"target_language": "en", "level": "D9"})
    assert r.status_code == 422


def test_creator_blocked_from_profile_post(client):
    _as_creator(client)
    r = client.post("/api/learner/profile", json=_PROFILE)
    assert r.status_code == 403


def test_unauthenticated_blocked_from_profile_post(client):
    r = client.post("/api/learner/profile", json=_PROFILE)
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# API: GET /api/learner/profile
# ---------------------------------------------------------------------------


def test_learner_can_get_profile(client):
    _as_learner(client)
    client.post("/api/learner/profile", json=_PROFILE)
    r = client.get("/api/learner/profile")
    assert r.status_code == 200
    assert r.json()["target_language"] == "en"
    assert r.json()["level"] == "B1"


def test_profile_not_found_before_onboarding(client):
    _as_learner(client)
    r = client.get("/api/learner/profile")
    assert r.status_code == 404


def test_creator_blocked_from_profile_get(client):
    _as_creator(client)
    r = client.get("/api/learner/profile")
    assert r.status_code == 403


def test_unauthenticated_blocked_from_profile_get(client):
    r = client.get("/api/learner/profile")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Feed gating
# ---------------------------------------------------------------------------


def test_feed_redirects_to_onboarding_when_no_profile(client):
    """Learner with no profile → /feed must 303 to /onboarding."""
    _as_learner(client)
    r = client.get("/feed", follow_redirects=False)
    assert r.status_code == 303
    assert "/onboarding" in r.headers["location"]


def test_feed_renders_for_learner_with_profile(client):
    _as_learner(client)
    client.post("/api/learner/profile", json=_PROFILE)
    r = client.get("/feed")
    assert r.status_code == 200
    assert b"Feed" in r.content


def test_creator_blocked_from_feed(client):
    _as_creator(client)
    r = client.get("/feed")
    assert r.status_code == 403


def test_unauthenticated_blocked_from_feed(client):
    r = client.get("/feed")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# SSR: GET /onboarding
# ---------------------------------------------------------------------------


def test_onboarding_page_renders_for_learner(client):
    _as_learner(client)
    r = client.get("/onboarding")
    assert r.status_code == 200
    assert b"target_language" in r.content
    assert b'name="csrf_token"' in r.content


def test_creator_blocked_from_onboarding_page(client):
    _as_creator(client)
    r = client.get("/onboarding")
    assert r.status_code == 403


def test_unauthenticated_blocked_from_onboarding(client):
    r = client.get("/onboarding")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# SSR: POST /onboarding
# ---------------------------------------------------------------------------


def test_onboarding_form_creates_profile_and_redirects_to_feed(client):
    _as_learner(client)
    r = client.post(
        "/onboarding",
        data={"target_language": "es", "level": "A1", "csrf_token": generate_csrf_token()},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/feed" in r.headers["location"]

    # Profile must now exist
    assert client.get("/api/learner/profile").json()["target_language"] == "es"


def test_onboarding_form_without_csrf_returns_403(client):
    _as_learner(client)
    r = client.post(
        "/onboarding",
        data={"target_language": "en", "level": "B1"},
    )
    assert r.status_code == 403


def test_onboarding_form_with_invalid_language_returns_400(client):
    _as_learner(client)
    r = client.post(
        "/onboarding",
        data={"target_language": "xx", "level": "B1", "csrf_token": generate_csrf_token()},
    )
    assert r.status_code == 400
