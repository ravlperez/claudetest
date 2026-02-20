"""
Acceptance criteria for TASK 14 — seed script:

- Seed creates demo creator + learner + 1 published content with 3-question quiz
- Learner has a profile (language=en, level=A1) so the feed is not empty on login
- Script is idempotent: second run returns False and inserts no duplicate rows
- After seeding, a logged-in learner sees the published content in the feed API
"""

import pytest
from sqlalchemy.orm import sessionmaker

from src.app.models import ContentStatus, Language, CEFRLevel, LearnerProfile, Role, User, VideoContent
from src.app.scripts.seed import (
    CREATOR_EMAIL,
    LEARNER_EMAIL,
    DEMO_PASSWORD,
    run,
)


# ── Local db_session fixture (same pattern as other test files) ───────────────

@pytest.fixture()
def db_session(db_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    db = Session()
    yield db
    db.close()


# ── Seed content tests ────────────────────────────────────────────────────────


def test_seed_creates_creator_user(db_session):
    run(db_session)
    user = db_session.query(User).filter(User.email == CREATOR_EMAIL).first()
    assert user is not None
    assert user.role == Role.creator


def test_seed_creates_learner_user(db_session):
    run(db_session)
    user = db_session.query(User).filter(User.email == LEARNER_EMAIL).first()
    assert user is not None
    assert user.role == Role.learner


def test_seed_learner_has_english_a1_profile(db_session):
    run(db_session)
    learner = db_session.query(User).filter(User.email == LEARNER_EMAIL).first()
    profile = db_session.get(LearnerProfile, learner.id)
    assert profile is not None
    assert profile.target_language == Language.en
    assert profile.level == CEFRLevel.A1


def test_seed_creates_published_content(db_session):
    run(db_session)
    content = db_session.query(VideoContent).filter(
        VideoContent.status == ContentStatus.published
    ).first()
    assert content is not None
    assert content.language == Language.en
    assert content.level == CEFRLevel.A1
    assert content.published_at is not None


def test_seed_content_has_3_question_quiz(db_session):
    run(db_session)
    content = db_session.query(VideoContent).filter(
        VideoContent.status == ContentStatus.published
    ).first()
    assert content.quiz is not None
    assert len(content.quiz.questions) == 3


def test_seed_returns_true_on_first_run(db_session):
    result = run(db_session)
    assert result is True


def test_seed_returns_false_when_already_seeded(db_session):
    run(db_session)
    result = run(db_session)
    assert result is False


def test_seed_is_idempotent_no_duplicates(db_session):
    """Running seed twice must not create duplicate user rows."""
    run(db_session)
    run(db_session)
    creator_count = db_session.query(User).filter(User.email == CREATOR_EMAIL).count()
    learner_count = db_session.query(User).filter(User.email == LEARNER_EMAIL).count()
    content_count = db_session.query(VideoContent).count()
    assert creator_count == 1
    assert learner_count == 1
    assert content_count == 1


def test_seed_demo_password_works(db_session):
    """Verify hashed password can be verified (login would succeed)."""
    import bcrypt
    run(db_session)
    creator = db_session.query(User).filter(User.email == CREATOR_EMAIL).first()
    assert bcrypt.checkpw(DEMO_PASSWORD.encode(), creator.password_hash.encode())


# ── Feed integration: after seeding, learner sees content ────────────────────


def test_seed_feed_is_not_empty_after_seeding(client):
    """After seeding, the learner's feed API returns at least one published video."""
    from src.app.database import get_db
    from src.app.scripts.seed import run as seed_run

    # Run seed using the test client's overridden DB
    db = next(client.app.dependency_overrides[get_db]())
    try:
        seed_run(db)
    finally:
        db.close()

    # Log in as the demo learner
    client.post(
        "/api/auth/login",
        json={"email": LEARNER_EMAIL, "password": DEMO_PASSWORD},
    )
    r = client.get("/api/feed")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) >= 1
    assert body["items"][0]["language"] == "en"
    assert body["items"][0]["level"] == "A1"
