"""
Acceptance criteria for TASK 11:

POST /api/creator/content/{id}/quiz  (creator only)
  - 401 unauthenticated, 403 learner, 404 not found, 403 wrong owner
  - 422 too few questions (< 3), too many questions (> 5)
  - 422 empty prompt, too few options (< 2), too many options (> 6)
  - 422 empty option string, correct_option_index out of range
  - 200 success: returns {quiz_id, question_count}
  - Replace semantics: second POST replaces first quiz entirely
  - After quiz creation: publish endpoint now succeeds (end-to-end)

GET /api/content/{id}/quiz  (learner only)
  - 401 unauthenticated, 403 creator
  - 404 content not found, 404 no quiz on published content
  - 409 content is a draft
  - 200 success: returns content + quiz with questions
  - Correct answer (correct_option_index) is NOT exposed to learner

SSR GET /creator/content/{id}/quiz
  - 200 for owning creator
  - 403 for wrong creator / learner
  - 401 unauthenticated
  - 404 for non-existent content
  - Page shows existing quiz data when quiz already exists
"""

import pytest
from sqlalchemy.orm import sessionmaker

from src.app.auth import hash_password
from src.app.models import (
    ContentStatus,
    Language,
    CEFRLevel,
    Role,
    User,
    VideoContent,
)

# ── Constants / helpers ────────────────────────────────────────────────────────

_CREATOR = {"email": "creator@example.com", "password": "pw123456", "role": "creator"}
_LEARNER = {"email": "learner@example.com", "password": "pw123456", "role": "learner"}

_VALID_CONTENT = {
    "language": "en",
    "level": "B1",
    "title": "Quiz test video",
    "video_url": "https://pub.example.com/videos/1/quiz.mp4",
}


def _valid_question(prompt: str = "What is correct?", n_options: int = 4, correct: int = 0) -> dict:
    return {
        "prompt": prompt,
        "options": [f"Option {i + 1}" for i in range(n_options)],
        "correct_option_index": correct,
    }


def _valid_quiz(n: int = 3) -> dict:
    return {"questions": [_valid_question(f"Question {i + 1}?") for i in range(n)]}


def _setup_creator_with_draft(client) -> int:
    """Sign up as creator, create a draft, return content_id."""
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.post("/api/creator/content", json=_VALID_CONTENT)
    assert r.status_code == 201
    return r.json()["id"]


def _setup_published(client) -> int:
    """
    Sign up as creator, create draft, add 3-question quiz, publish.
    Returns content_id. Client is still authenticated as creator after this.
    """
    content_id = _setup_creator_with_draft(client)
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=_valid_quiz(3))
    assert r.status_code == 200
    r = client.post(f"/api/creator/content/{content_id}/publish")
    assert r.status_code == 200
    return content_id


# ── POST /api/creator/content/{id}/quiz — auth ────────────────────────────────


def test_create_quiz_unauthenticated_returns_401(client):
    r = client.post("/api/creator/content/1/quiz", json=_valid_quiz())
    assert r.status_code == 401


def test_create_quiz_learner_returns_403(client):
    client.post("/api/auth/signup", json=_LEARNER)
    r = client.post("/api/creator/content/1/quiz", json=_valid_quiz())
    assert r.status_code == 403


def test_create_quiz_not_found_returns_404(client):
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.post("/api/creator/content/9999/quiz", json=_valid_quiz())
    assert r.status_code == 404


def test_create_quiz_wrong_creator_returns_403(client, db_engine):
    """Creator A cannot add a quiz to creator B's content."""
    client.post("/api/auth/signup", json=_CREATOR)

    # Seed creator B + their content directly
    Session = sessionmaker(bind=db_engine)
    db = Session()
    creator_b = User(
        email="b@example.com",
        password_hash=hash_password("pw"),
        role=Role.creator,
    )
    db.add(creator_b)
    db.flush()
    content_b = VideoContent(
        creator_id=creator_b.id,
        language=Language.en,
        level=CEFRLevel.B1,
        title="B video",
        video_url="https://pub.example.com/b.mp4",
        status=ContentStatus.draft,
    )
    db.add(content_b)
    db.commit()
    content_b_id = content_b.id
    db.close()

    r = client.post(f"/api/creator/content/{content_b_id}/quiz", json=_valid_quiz())
    assert r.status_code == 403


# ── POST /api/creator/content/{id}/quiz — question count validation ───────────


def test_create_quiz_zero_questions_returns_422(client):
    content_id = _setup_creator_with_draft(client)
    r = client.post(f"/api/creator/content/{content_id}/quiz", json={"questions": []})
    assert r.status_code == 422


def test_create_quiz_two_questions_returns_422(client):
    content_id = _setup_creator_with_draft(client)
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=_valid_quiz(2))
    assert r.status_code == 422


def test_create_quiz_six_questions_returns_422(client):
    content_id = _setup_creator_with_draft(client)
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=_valid_quiz(6))
    assert r.status_code == 422


def test_create_quiz_exactly_three_questions_succeeds(client):
    content_id = _setup_creator_with_draft(client)
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=_valid_quiz(3))
    assert r.status_code == 200
    assert r.json()["question_count"] == 3


def test_create_quiz_exactly_five_questions_succeeds(client):
    content_id = _setup_creator_with_draft(client)
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=_valid_quiz(5))
    assert r.status_code == 200
    assert r.json()["question_count"] == 5


# ── POST /api/creator/content/{id}/quiz — question field validation ───────────


def test_create_quiz_empty_prompt_returns_422(client):
    content_id = _setup_creator_with_draft(client)
    bad = _valid_quiz(3)
    bad["questions"][0]["prompt"] = "   "  # whitespace-only
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=bad)
    assert r.status_code == 422


def test_create_quiz_one_option_returns_422(client):
    content_id = _setup_creator_with_draft(client)
    bad = _valid_quiz(3)
    bad["questions"][0]["options"] = ["Only one"]
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=bad)
    assert r.status_code == 422


def test_create_quiz_seven_options_returns_422(client):
    content_id = _setup_creator_with_draft(client)
    bad = _valid_quiz(3)
    bad["questions"][0]["options"] = [f"Opt {i}" for i in range(7)]
    bad["questions"][0]["correct_option_index"] = 0
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=bad)
    assert r.status_code == 422


def test_create_quiz_empty_option_string_returns_422(client):
    content_id = _setup_creator_with_draft(client)
    bad = _valid_quiz(3)
    bad["questions"][0]["options"] = ["Valid option", "  "]  # second option is whitespace
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=bad)
    assert r.status_code == 422


def test_create_quiz_correct_index_negative_returns_422(client):
    content_id = _setup_creator_with_draft(client)
    bad = _valid_quiz(3)
    bad["questions"][0]["correct_option_index"] = -1
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=bad)
    assert r.status_code == 422


def test_create_quiz_correct_index_out_of_range_returns_422(client):
    content_id = _setup_creator_with_draft(client)
    bad = _valid_quiz(3)
    # 4 options, so valid indices are 0-3; index 4 is out of range
    bad["questions"][0]["options"] = ["A", "B", "C", "D"]
    bad["questions"][0]["correct_option_index"] = 4
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=bad)
    assert r.status_code == 422


# ── POST /api/creator/content/{id}/quiz — success ────────────────────────────


def test_create_quiz_returns_quiz_id_and_count(client):
    content_id = _setup_creator_with_draft(client)
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=_valid_quiz(4))
    assert r.status_code == 200
    body = r.json()
    assert "quiz_id" in body
    assert isinstance(body["quiz_id"], int)
    assert body["question_count"] == 4


def test_create_quiz_with_two_options_succeeds(client):
    """Minimum valid options per question is 2."""
    content_id = _setup_creator_with_draft(client)
    quiz = {
        "questions": [
            {"prompt": "True or false?", "options": ["True", "False"], "correct_option_index": 0},
            {"prompt": "Yes or no?", "options": ["Yes", "No"], "correct_option_index": 1},
            {"prompt": "A or B?", "options": ["A", "B"], "correct_option_index": 0},
        ]
    }
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=quiz)
    assert r.status_code == 200
    assert r.json()["question_count"] == 3


def test_create_quiz_with_six_options_succeeds(client):
    """Maximum valid options per question is 6."""
    content_id = _setup_creator_with_draft(client)
    quiz = {
        "questions": [
            {
                "prompt": "Pick one",
                "options": ["A", "B", "C", "D", "E", "F"],
                "correct_option_index": 5,
            }
        ]
        + [_valid_question(f"Q{i}") for i in range(2)]
    }
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=quiz)
    assert r.status_code == 200


def test_create_quiz_replaces_existing_quiz(client):
    """POSTing a second quiz replaces the first; question_count reflects new quiz."""
    content_id = _setup_creator_with_draft(client)

    r1 = client.post(f"/api/creator/content/{content_id}/quiz", json=_valid_quiz(3))
    assert r1.status_code == 200
    quiz_id_1 = r1.json()["quiz_id"]

    r2 = client.post(f"/api/creator/content/{content_id}/quiz", json=_valid_quiz(5))
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["question_count"] == 5
    # quiz_id is present (replace may reuse the same id in SQLite, which is fine)
    assert "quiz_id" in body2


def test_quiz_enables_publish(client):
    """Full flow: create draft → add quiz → publish → 200."""
    content_id = _setup_creator_with_draft(client)
    r = client.post(f"/api/creator/content/{content_id}/quiz", json=_valid_quiz(3))
    assert r.status_code == 200

    r = client.post(f"/api/creator/content/{content_id}/publish")
    assert r.status_code == 200
    assert r.json()["status"] == "published"


# ── GET /api/content/{id}/quiz — auth ─────────────────────────────────────────


def test_get_quiz_unauthenticated_returns_401(client):
    r = client.get("/api/content/1/quiz")
    assert r.status_code == 401


def test_get_quiz_creator_returns_403(client):
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.get("/api/content/1/quiz")
    assert r.status_code == 403


# ── GET /api/content/{id}/quiz — not found / not published ────────────────────


def test_get_quiz_content_not_found_returns_404(client):
    client.post("/api/auth/signup", json=_LEARNER)
    r = client.get("/api/content/9999/quiz")
    assert r.status_code == 404


def test_get_quiz_draft_content_returns_409(client):
    """Learner cannot access the quiz for a draft (unpublished) content."""
    content_id = _setup_creator_with_draft(client)
    # Add quiz but do NOT publish
    client.post(f"/api/creator/content/{content_id}/quiz", json=_valid_quiz(3))

    # Switch to learner
    client.post("/api/auth/signup", json=_LEARNER)
    r = client.get(f"/api/content/{content_id}/quiz")
    assert r.status_code == 409


def test_get_quiz_no_quiz_on_published_returns_404(client, db_engine):
    """Published content with no quiz → 404 (edge case)."""
    # Directly seed a published content WITHOUT a quiz
    Session = sessionmaker(bind=db_engine)
    db = Session()
    creator = User(
        email="c@example.com",
        password_hash=hash_password("pw"),
        role=Role.creator,
    )
    db.add(creator)
    db.flush()
    content = VideoContent(
        creator_id=creator.id,
        language=Language.en,
        level=CEFRLevel.A1,
        title="No quiz",
        video_url="https://pub.example.com/noquiz.mp4",
        status=ContentStatus.published,
    )
    db.add(content)
    db.commit()
    content_id = content.id
    db.close()

    client.post("/api/auth/signup", json=_LEARNER)
    r = client.get(f"/api/content/{content_id}/quiz")
    assert r.status_code == 404


# ── GET /api/content/{id}/quiz — success ──────────────────────────────────────


def test_get_quiz_returns_correct_shape(client):
    """Learner receives content metadata + quiz with questions (no correct answers)."""
    content_id = _setup_published(client)

    # Switch to learner
    client.post("/api/auth/signup", json=_LEARNER)
    r = client.get(f"/api/content/{content_id}/quiz")
    assert r.status_code == 200

    body = r.json()
    assert body["content"]["id"] == content_id
    assert "title" in body["content"]
    assert "video_url" in body["content"]
    assert "id" in body["quiz"]
    assert len(body["quiz"]["questions"]) == 3


def test_get_quiz_questions_have_required_fields(client):
    content_id = _setup_published(client)

    client.post("/api/auth/signup", json=_LEARNER)
    r = client.get(f"/api/content/{content_id}/quiz")
    assert r.status_code == 200

    q = r.json()["quiz"]["questions"][0]
    assert "id" in q
    assert q["type"] == "multiple_choice"
    assert "prompt" in q
    assert isinstance(q["options"], list)
    assert len(q["options"]) >= 2


def test_get_quiz_does_not_expose_correct_answer(client):
    """correct_option_index must NOT appear in the learner-facing response."""
    content_id = _setup_published(client)

    client.post("/api/auth/signup", json=_LEARNER)
    r = client.get(f"/api/content/{content_id}/quiz")
    assert r.status_code == 200

    for q in r.json()["quiz"]["questions"]:
        assert "correct_option_index" not in q, (
            "correct_option_index must not be exposed in GET /api/content/{id}/quiz"
        )


# ── SSR GET /creator/content/{id}/quiz ────────────────────────────────────────


def test_quiz_form_renders_for_creator(client):
    content_id = _setup_creator_with_draft(client)
    r = client.get(f"/creator/content/{content_id}/quiz")
    assert r.status_code == 200
    assert b"Save Quiz" in r.content
    assert b"quiz-form" in r.content


def test_quiz_form_blocked_for_learner(client):
    client.post("/api/auth/signup", json=_LEARNER)
    r = client.get("/creator/content/1/quiz")
    assert r.status_code == 403


def test_quiz_form_blocked_for_unauthenticated(client):
    r = client.get("/creator/content/1/quiz")
    assert r.status_code == 401


def test_quiz_form_not_found_returns_404(client):
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.get("/creator/content/9999/quiz")
    assert r.status_code == 404


def test_quiz_form_shows_existing_quiz_data(client):
    """When a quiz exists, its prompt text is embedded in the page for pre-fill."""
    content_id = _setup_creator_with_draft(client)
    quiz = {
        "questions": [
            {
                "prompt": "UniquePromptXYZ123",
                "options": ["A", "B", "C"],
                "correct_option_index": 1,
            },
            _valid_question("Q2"),
            _valid_question("Q3"),
        ]
    }
    client.post(f"/api/creator/content/{content_id}/quiz", json=quiz)

    r = client.get(f"/creator/content/{content_id}/quiz")
    assert r.status_code == 200
    # The existing quiz data is embedded as JSON in the page for JS pre-fill
    assert b"UniquePromptXYZ123" in r.content
