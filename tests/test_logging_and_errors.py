"""
Tests for TASK 15 — structured logging and consistent error handler.

Covers:
- auth_login_success / auth_login_failure log events
- creator_publish log event
- learner_attempt_submitted log event (with score + xp_awarded)
- Unhandled exceptions return {"error": {"code": ..., "message": ...}} JSON (not stack trace)
"""

import logging

import pytest
from fastapi.testclient import TestClient

from src.app.database import get_db
from src.app.main import app


# ── Helpers ───────────────────────────────────────────────────────────────────


def _signup(client, email, password, role="learner"):
    client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "role": role},
    )


def _login(client, email, password):
    client.post("/api/auth/login", json={"email": email, "password": password})


def _make_published_content(client):
    """Create and publish a 3-question content item; return its content_id."""
    r = client.post(
        "/api/creator/content",
        json={
            "language": "en",
            "level": "A1",
            "title": "Logging test video",
            "video_url": "https://example.com/v.mp4",
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    client.post(
        f"/api/creator/content/{cid}/quiz",
        json={
            "questions": [
                {"prompt": "Q1?", "options": ["A", "B"], "correct_option_index": 0},
                {"prompt": "Q2?", "options": ["A", "B"], "correct_option_index": 1},
                {"prompt": "Q3?", "options": ["A", "B"], "correct_option_index": 0},
            ]
        },
    )
    return cid


# ── Login logging ─────────────────────────────────────────────────────────────


def test_login_success_is_logged(client, caplog):
    _signup(client, "u@x.com", "pass1234", role="creator")
    client.cookies.clear()

    with caplog.at_level(logging.INFO, logger="src.app.routers.auth"):
        _login(client, "u@x.com", "pass1234")

    messages = [r.message for r in caplog.records]
    assert any("auth_login_success" in m for m in messages)


def test_login_failure_is_logged(client, caplog):
    with caplog.at_level(logging.WARNING, logger="src.app.routers.auth"):
        r = client.post(
            "/api/auth/login",
            json={"email": "nobody@x.com", "password": "wrongpass"},
        )

    assert r.status_code == 401
    messages = [r.message for r in caplog.records]
    assert any("auth_login_failure" in m for m in messages)


def test_login_success_log_includes_email(client, caplog):
    _signup(client, "user@example.com", "pass1234")
    client.cookies.clear()

    with caplog.at_level(logging.INFO, logger="src.app.routers.auth"):
        _login(client, "user@example.com", "pass1234")

    messages = " ".join(r.message for r in caplog.records)
    assert "user@example.com" in messages


def test_login_failure_log_includes_email(client, caplog):
    with caplog.at_level(logging.WARNING, logger="src.app.routers.auth"):
        client.post(
            "/api/auth/login",
            json={"email": "missing@example.com", "password": "bad"},
        )

    messages = " ".join(r.message for r in caplog.records)
    assert "missing@example.com" in messages


# ── Publish logging ───────────────────────────────────────────────────────────


def test_publish_is_logged(client, caplog):
    _signup(client, "creator@x.com", "pass1234", role="creator")
    cid = _make_published_content(client)

    with caplog.at_level(logging.INFO, logger="src.app.routers.creator"):
        r = client.post(f"/api/creator/content/{cid}/publish")

    assert r.status_code == 200
    messages = [r.message for r in caplog.records]
    assert any("creator_publish" in m for m in messages)


def test_publish_log_includes_content_id(client, caplog):
    _signup(client, "creator2@x.com", "pass1234", role="creator")
    cid = _make_published_content(client)

    with caplog.at_level(logging.INFO, logger="src.app.routers.creator"):
        client.post(f"/api/creator/content/{cid}/publish")

    messages = " ".join(r.message for r in caplog.records)
    assert f"content_id={cid}" in messages


# ── Attempt logging ───────────────────────────────────────────────────────────


def test_attempt_submission_is_logged(client, caplog):
    # Set up: creator publishes content
    _signup(client, "cr@x.com", "pass1234", role="creator")
    cid = _make_published_content(client)
    client.post(f"/api/creator/content/{cid}/publish")
    client.cookies.clear()

    # Set up: learner with profile
    _signup(client, "lr@x.com", "pass1234", role="learner")
    client.post("/api/learner/profile", json={"target_language": "en", "level": "A1"})

    # Get question IDs
    qr = client.get(f"/api/content/{cid}/quiz")
    assert qr.status_code == 200
    questions = qr.json()["quiz"]["questions"]
    answers = [{"question_id": q["id"], "selected_index": 0} for q in questions]

    with caplog.at_level(logging.INFO, logger="src.app.routers.learner"):
        r = client.post(f"/api/content/{cid}/attempt", json={"answers": answers})

    assert r.status_code == 201
    messages = [r.message for r in caplog.records]
    assert any("learner_attempt_submitted" in m for m in messages)


def test_attempt_log_includes_score_and_xp(client, caplog):
    _signup(client, "cr2@x.com", "pass1234", role="creator")
    cid = _make_published_content(client)
    client.post(f"/api/creator/content/{cid}/publish")
    client.cookies.clear()

    _signup(client, "lr2@x.com", "pass1234", role="learner")
    client.post("/api/learner/profile", json={"target_language": "en", "level": "A1"})
    qr = client.get(f"/api/content/{cid}/quiz")
    questions = qr.json()["quiz"]["questions"]
    answers = [{"question_id": q["id"], "selected_index": 0} for q in questions]

    with caplog.at_level(logging.INFO, logger="src.app.routers.learner"):
        client.post(f"/api/content/{cid}/attempt", json={"answers": answers})

    messages = " ".join(r.message for r in caplog.records)
    assert "score=" in messages
    assert "xp_awarded=" in messages


# ── Error handler ─────────────────────────────────────────────────────────────


def test_unhandled_exception_returns_json_500():
    """RuntimeError from a dependency must return clean JSON, not a stack trace."""

    def _bad_db():
        raise RuntimeError("Simulated database crash")
        yield  # unreachable — makes this a generator as required by FastAPI Depends

    app.dependency_overrides[get_db] = _bad_db
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(
                "/api/auth/signup",
                json={"email": "test@example.com", "password": "pass1234"},
            )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 500
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == "internal_error"
    assert "message" in data["error"]


def test_unhandled_exception_body_has_no_traceback():
    """Response body must not contain Python traceback text."""

    def _bad_db():
        raise RuntimeError("Traceback check")
        yield

    app.dependency_overrides[get_db] = _bad_db
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(
                "/api/auth/signup",
                json={"email": "test2@example.com", "password": "pass1234"},
            )
    finally:
        app.dependency_overrides.clear()

    assert "Traceback" not in r.text
    assert "RuntimeError" not in r.text
