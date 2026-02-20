"""
Acceptance criteria for TASK 10:
- Creator can create a content draft via POST /api/creator/content (201)
- Draft appears in GET /api/creator/content list
- GET /api/creator/content returns empty list when no content exists
- Learner blocked from all creator content endpoints (403)
- Unauthenticated blocked from all creator content endpoints (401)
- Invalid language / level → 422
- Publish without quiz → 409
- Publish with quiz but < 3 questions → 409
- Publish with quiz but > 5 questions → 409
- Publish with 3–5 questions → 200, status=published, published_at set
- Publish is idempotent (second call → 200, already published)
- Creator cannot publish another creator's content → 403
- Non-existent content → 404
- SSR: GET /creator renders dashboard (200) for creator, 403 for learner, 401 for anon
- SSR: GET /creator/content/new renders form (200) for creator
- SSR: POST /creator/content creates draft and redirects to detail page (303)
- SSR: POST /creator/content without CSRF → 403
- SSR: GET /creator/content/{id} renders detail (200) for owning creator
- SSR: GET /creator/content/{id} → 403 for non-owning creator

VideoContent and Quiz/Question rows are inserted via a local db_session fixture
(same in-memory SQLite engine as the TestClient) to keep tests self-contained.
"""

import json

import pytest
from sqlalchemy.orm import sessionmaker

from src.app.auth import hash_password
from src.app.csrf import generate_csrf_token
from src.app.models import (
    CEFRLevel,
    ContentStatus,
    Language,
    Question,
    Quiz,
    Role,
    User,
    VideoContent,
)

# ── Local fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(db_engine):
    """Bare SQLAlchemy session sharing the same in-memory DB as the TestClient."""
    Session = sessionmaker(bind=db_engine)
    sess = Session()
    yield sess
    sess.close()


# ── Helpers ────────────────────────────────────────────────────────────────────

_CREATOR = {"email": "creator@example.com", "password": "pw123456", "role": "creator"}
_CREATOR2 = {"email": "creator2@example.com", "password": "pw123456", "role": "creator"}
_LEARNER = {"email": "learner@example.com", "password": "pw123456", "role": "learner"}

_VALID_CONTENT = {
    "language": "en",
    "level": "A2",
    "title": "Past simple in 30s",
    "video_url": "https://pub.example.com/videos/1/abc.mp4",
}


def _signup(client, user=_CREATOR):
    client.post("/api/auth/signup", json=user)


def _signup_creator(client):
    _signup(client, _CREATOR)


def _signup_creator2(client):
    """Sign up a second creator (uses a fresh client cookie jar trick)."""
    # We POST without replacing the existing session — use cookies directly
    client.post("/api/auth/signup", json=_CREATOR2)


def _signup_learner(client):
    _signup(client, _LEARNER)


def _create_draft(client, payload=None) -> dict:
    """Create a content draft via the JSON API; return parsed response body."""
    if payload is None:
        payload = _VALID_CONTENT
    r = client.post("/api/creator/content", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _seed_quiz(db_session, content_id: int, n_questions: int) -> Quiz:
    """Directly insert a Quiz with n_questions Questions into the test DB."""
    quiz = Quiz(content_id=content_id)
    db_session.add(quiz)
    db_session.flush()
    for i in range(n_questions):
        q = Question(
            quiz_id=quiz.id,
            prompt=f"Question {i + 1}?",
            options_json=json.dumps(["A", "B", "C", "D"]),
            correct_option_index=0,
        )
        db_session.add(q)
    db_session.commit()
    return quiz


# ── GET /api/creator/content — auth ────────────────────────────────────────────


def test_list_content_unauthenticated_returns_401(client):
    r = client.get("/api/creator/content")
    assert r.status_code == 401


def test_list_content_learner_returns_403(client):
    _signup_learner(client)
    r = client.get("/api/creator/content")
    assert r.status_code == 403


# ── GET /api/creator/content — success ────────────────────────────────────────


def test_list_content_empty_for_new_creator(client):
    _signup_creator(client)
    r = client.get("/api/creator/content")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_list_content_shows_created_draft(client):
    _signup_creator(client)
    body = _create_draft(client)
    r = client.get("/api/creator/content")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == body["id"]
    assert items[0]["status"] == "draft"
    assert items[0]["title"] == _VALID_CONTENT["title"]


def test_list_content_only_shows_own_content(client, db_session):
    """Creator sees only their own content, not other creators'."""
    _signup_creator(client)
    _create_draft(client)

    # Seed a second creator's content directly in the DB
    creator2 = User(
        email="other@example.com",
        password_hash=hash_password("pw123456"),
        role=Role.creator,
    )
    db_session.add(creator2)
    db_session.flush()
    other_content = VideoContent(
        creator_id=creator2.id,
        language=Language.es,
        level=CEFRLevel.B1,
        title="Other creator's video",
        video_url="https://pub.example.com/videos/other.mp4",
        status=ContentStatus.draft,
    )
    db_session.add(other_content)
    db_session.commit()

    r = client.get("/api/creator/content")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1  # only own content


# ── POST /api/creator/content — auth ──────────────────────────────────────────


def test_create_content_unauthenticated_returns_401(client):
    r = client.post("/api/creator/content", json=_VALID_CONTENT)
    assert r.status_code == 401


def test_create_content_learner_returns_403(client):
    _signup_learner(client)
    r = client.post("/api/creator/content", json=_VALID_CONTENT)
    assert r.status_code == 403


# ── POST /api/creator/content — validation ────────────────────────────────────


def test_create_content_invalid_language_returns_422(client):
    _signup_creator(client)
    bad = {**_VALID_CONTENT, "language": "de"}
    r = client.post("/api/creator/content", json=bad)
    assert r.status_code == 422


def test_create_content_invalid_level_returns_422(client):
    _signup_creator(client)
    bad = {**_VALID_CONTENT, "level": "D1"}
    r = client.post("/api/creator/content", json=bad)
    assert r.status_code == 422


def test_create_content_empty_title_returns_422(client):
    _signup_creator(client)
    bad = {**_VALID_CONTENT, "title": "   "}
    r = client.post("/api/creator/content", json=bad)
    assert r.status_code == 422


def test_create_content_empty_video_url_returns_422(client):
    _signup_creator(client)
    bad = {**_VALID_CONTENT, "video_url": "  "}
    r = client.post("/api/creator/content", json=bad)
    assert r.status_code == 422


# ── POST /api/creator/content — success ───────────────────────────────────────


def test_create_content_returns_201_with_draft_status(client):
    _signup_creator(client)
    r = client.post("/api/creator/content", json=_VALID_CONTENT)
    assert r.status_code == 201
    body = r.json()
    assert "id" in body
    assert body["status"] == "draft"


def test_create_content_with_caption(client):
    _signup_creator(client)
    payload = {**_VALID_CONTENT, "caption": "A short caption."}
    r = client.post("/api/creator/content", json=payload)
    assert r.status_code == 201


def test_create_content_appears_in_list(client):
    _signup_creator(client)
    created = _create_draft(client)
    items = client.get("/api/creator/content").json()["items"]
    ids = [i["id"] for i in items]
    assert created["id"] in ids


# ── POST /api/creator/content/{id}/publish — auth ─────────────────────────────


def test_publish_unauthenticated_returns_401(client):
    r = client.post("/api/creator/content/1/publish")
    assert r.status_code == 401


def test_publish_learner_returns_403(client):
    _signup_learner(client)
    r = client.post("/api/creator/content/1/publish")
    assert r.status_code == 403


# ── POST /api/creator/content/{id}/publish — not found ────────────────────────


def test_publish_nonexistent_content_returns_404(client):
    _signup_creator(client)
    r = client.post("/api/creator/content/9999/publish")
    assert r.status_code == 404


# ── POST /api/creator/content/{id}/publish — ownership ───────────────────────


def test_publish_other_creators_content_returns_403(client, db_session):
    """Creator A cannot publish content owned by creator B."""
    _signup_creator(client)  # logs in as creator A

    # Seed creator B's content directly in DB
    creator_b = User(
        email="b@example.com",
        password_hash=hash_password("pw123456"),
        role=Role.creator,
    )
    db_session.add(creator_b)
    db_session.flush()
    content_b = VideoContent(
        creator_id=creator_b.id,
        language=Language.en,
        level=CEFRLevel.A2,
        title="Creator B video",
        video_url="https://pub.example.com/videos/b.mp4",
        status=ContentStatus.draft,
    )
    db_session.add(content_b)
    db_session.commit()

    r = client.post(f"/api/creator/content/{content_b.id}/publish")
    assert r.status_code == 403


# ── POST /api/creator/content/{id}/publish — quiz constraints ─────────────────


def test_publish_without_quiz_returns_409(client):
    _signup_creator(client)
    draft = _create_draft(client)
    r = client.post(f"/api/creator/content/{draft['id']}/publish")
    assert r.status_code == 409
    assert "quiz" in r.json()["detail"].lower()


def test_publish_with_too_few_questions_returns_409(client, db_session):
    _signup_creator(client)
    draft = _create_draft(client)
    _seed_quiz(db_session, draft["id"], n_questions=2)  # 2 < 3
    r = client.post(f"/api/creator/content/{draft['id']}/publish")
    assert r.status_code == 409
    assert "2" in r.json()["detail"]  # "currently has 2"


def test_publish_with_too_many_questions_returns_409(client, db_session):
    _signup_creator(client)
    draft = _create_draft(client)
    _seed_quiz(db_session, draft["id"], n_questions=6)  # 6 > 5
    r = client.post(f"/api/creator/content/{draft['id']}/publish")
    assert r.status_code == 409
    assert "6" in r.json()["detail"]  # "currently has 6"


# ── POST /api/creator/content/{id}/publish — success ─────────────────────────


def test_publish_with_3_questions_succeeds(client, db_session):
    _signup_creator(client)
    draft = _create_draft(client)
    _seed_quiz(db_session, draft["id"], n_questions=3)
    r = client.post(f"/api/creator/content/{draft['id']}/publish")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "published"
    assert body["published_at"] is not None
    assert body["id"] == draft["id"]


def test_publish_with_5_questions_succeeds(client, db_session):
    _signup_creator(client)
    draft = _create_draft(client)
    _seed_quiz(db_session, draft["id"], n_questions=5)
    r = client.post(f"/api/creator/content/{draft['id']}/publish")
    assert r.status_code == 200
    assert r.json()["status"] == "published"


def test_publish_updates_status_in_list(client, db_session):
    """After publish, GET /api/creator/content shows status=published."""
    _signup_creator(client)
    draft = _create_draft(client)
    _seed_quiz(db_session, draft["id"], n_questions=3)
    client.post(f"/api/creator/content/{draft['id']}/publish")

    items = client.get("/api/creator/content").json()["items"]
    item = next(i for i in items if i["id"] == draft["id"])
    assert item["status"] == "published"
    assert item["published_at"] is not None


def test_publish_is_idempotent(client, db_session):
    """Calling publish a second time returns 200 (not an error)."""
    _signup_creator(client)
    draft = _create_draft(client)
    _seed_quiz(db_session, draft["id"], n_questions=3)
    r1 = client.post(f"/api/creator/content/{draft['id']}/publish")
    assert r1.status_code == 200
    r2 = client.post(f"/api/creator/content/{draft['id']}/publish")
    assert r2.status_code == 200
    assert r2.json()["status"] == "published"


# ── SSR: GET /creator — dashboard ─────────────────────────────────────────────


def test_dashboard_renders_for_creator(client):
    _signup_creator(client)
    r = client.get("/creator")
    assert r.status_code == 200
    assert b"Creator Dashboard" in r.content


def test_dashboard_shows_empty_state_when_no_content(client):
    _signup_creator(client)
    r = client.get("/creator")
    assert r.status_code == 200
    assert b"empty-state" in r.content


def test_dashboard_blocked_for_learner(client):
    _signup_learner(client)
    r = client.get("/creator")
    assert r.status_code == 403


def test_dashboard_blocked_for_unauthenticated(client):
    r = client.get("/creator")
    assert r.status_code == 401


def test_dashboard_shows_content_title(client):
    _signup_creator(client)
    _create_draft(client)
    r = client.get("/creator")
    assert r.status_code == 200
    assert b"Past simple in 30s" in r.content


# ── SSR: GET /creator/content/new ─────────────────────────────────────────────


def test_content_new_form_renders_for_creator(client):
    _signup_creator(client)
    r = client.get("/creator/content/new")
    assert r.status_code == 200
    assert b"csrf_token" in r.content
    assert b"video_url" in r.content


def test_content_new_form_blocked_for_learner(client):
    _signup_learner(client)
    r = client.get("/creator/content/new")
    assert r.status_code == 403


# ── SSR: POST /creator/content (form) ─────────────────────────────────────────


def test_content_form_creates_draft_and_redirects(client):
    _signup_creator(client)
    r = client.post(
        "/creator/content",
        data={
            "title": "Form Video",
            "language": "es",
            "level": "B1",
            "video_url": "https://pub.example.com/videos/form.mp4",
            "caption": "",
            "csrf_token": generate_csrf_token(),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    location = r.headers["location"]
    assert location.startswith("/creator/content/")

    # Follow redirect → detail page
    r2 = client.get(location)
    assert r2.status_code == 200
    assert b"Form Video" in r2.content


def test_content_form_without_csrf_returns_403(client):
    _signup_creator(client)
    r = client.post(
        "/creator/content",
        data={
            "title": "No CSRF",
            "language": "en",
            "level": "A1",
            "video_url": "https://pub.example.com/videos/x.mp4",
            # no csrf_token
        },
        follow_redirects=False,
    )
    assert r.status_code == 403


# ── SSR: GET /creator/content/{id} ────────────────────────────────────────────


def test_content_detail_renders_for_creator(client):
    _signup_creator(client)
    draft = _create_draft(client)
    r = client.get(f"/creator/content/{draft['id']}")
    assert r.status_code == 200
    assert b"Past simple in 30s" in r.content
    assert b"quiz-missing" in r.content  # no quiz yet → id="quiz-missing" element


def test_content_detail_shows_publish_button_when_ready(client, db_session):
    _signup_creator(client)
    draft = _create_draft(client)
    _seed_quiz(db_session, draft["id"], n_questions=3)
    r = client.get(f"/creator/content/{draft['id']}")
    assert r.status_code == 200
    assert b"publish-btn" in r.content


def test_content_detail_blocked_for_other_creator(client, db_session):
    """A creator cannot view another creator's content detail page."""
    _signup_creator(client)
    draft = _create_draft(client)

    # Now switch to creator2 by overwriting the session cookie
    client.post("/api/auth/signup", json=_CREATOR2)

    r = client.get(f"/creator/content/{draft['id']}")
    assert r.status_code == 403


def test_content_detail_not_found_returns_404(client):
    _signup_creator(client)
    r = client.get("/creator/content/9999")
    assert r.status_code == 404
