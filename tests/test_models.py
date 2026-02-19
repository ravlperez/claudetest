"""
Acceptance criteria for TASK 4:
- Migration can be generated and applied  (verified by running alembic upgrade head)
- Simple script can create a user row     (verified by this test)

Uses an in-memory SQLite so the test is self-contained and does not depend on
the presence of data/app.db or any prior alembic run.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.app.database import Base
import src.app.models  # registers all 9 models with Base.metadata  # noqa: F401
from src.app.models import Language, CEFRLevel, ContentStatus, Role, User, LearnerProfile


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_user_row_insert_and_read():
    """All tables are created in-memory and a User row is insertable/readable."""
    Session = _make_session()
    with Session() as session:
        user = User(
            email="test@example.com",
            password_hash="not-a-real-hash",
            role=Role.learner,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.role == Role.learner
    assert user.created_at is not None


def test_learner_profile_fk():
    """LearnerProfile foreign-key to User works and defaults are applied."""
    Session = _make_session()
    with Session() as session:
        user = User(
            email="learner@example.com",
            password_hash="hash",
            role=Role.learner,
        )
        session.add(user)
        session.flush()  # get user.id without committing
        user_id = user.id  # capture before session closes

        profile = LearnerProfile(
            user_id=user_id,
            target_language=Language.en,
            level=CEFRLevel.A2,
        )
        session.add(profile)
        session.commit()
        session.refresh(profile)

        # Assert inside the session while objects are still attached
        assert profile.user_id == user_id
        assert profile.target_language == Language.en
        assert profile.level == CEFRLevel.A2
        assert profile.total_xp == 0
