"""
Demo seed script — creates demo accounts and one published content item.

Usage:
    alembic upgrade head            # run migrations first (creates data/app.db)
    python -m src.app.scripts.seed  # insert demo data

Demo credentials:
    Creator  →  demo.creator@langapp.dev  /  Demo1234!
    Learner  →  demo.learner@langapp.dev  /  Demo1234!

Idempotency:
    If the creator demo account already exists the script prints a warning
    and exits without inserting duplicate rows. Safe to run multiple times.

Placeholder video:
    The seeded content uses a publicly available sample MP4. Replace
    video_url with a real R2 URL when running a live demo.
"""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.app.auth import hash_password
from src.app.database import SessionLocal
from src.app.models import (
    CEFRLevel,
    ContentStatus,
    Language,
    LearnerProfile,
    Question,
    Quiz,
    Role,
    User,
    VideoContent,
)

# ── Demo credentials ──────────────────────────────────────────────────────────

CREATOR_EMAIL = "demo.creator@langapp.dev"
LEARNER_EMAIL = "demo.learner@langapp.dev"
DEMO_PASSWORD = "Demo1234!"

# Public-domain sample MP4 (replace with a real R2 URL for a live demo).
_PLACEHOLDER_VIDEO_URL = (
    "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
)

# ── Seed data ─────────────────────────────────────────────────────────────────

_QUESTIONS = [
    (
        "Which phrase is a common English greeting?",
        ["Bonjour", "Hello", "Hola", "Ciao"],
        1,  # "Hello"
    ),
    (
        "What do you say when leaving someone?",
        ["Good morning", "How are you?", "Goodbye", "Please"],
        2,  # "Goodbye"
    ),
    (
        "How do you ask someone how they are feeling?",
        ["What is your name?", "How are you?", "Where are you from?", "Thank you"],
        1,  # "How are you?"
    ),
]


def run(db: Session) -> bool:
    """
    Seed demo data into the given session.

    Returns True if data was inserted, False if already present (idempotent).
    The caller is responsible for the session lifecycle (commit is done here).
    """
    # Idempotency: bail out if demo creator already exists
    if db.query(User).filter(User.email == CREATOR_EMAIL).first():
        print(
            f"[seed] Demo data already present ('{CREATOR_EMAIL}' exists). Skipping."
        )
        return False

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # ── Creator ───────────────────────────────────────────────────────────────
    creator = User(
        email=CREATOR_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        role=Role.creator,
        created_at=now,
    )
    db.add(creator)
    db.flush()

    # ── Learner + profile ─────────────────────────────────────────────────────
    learner = User(
        email=LEARNER_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        role=Role.learner,
        created_at=now,
    )
    db.add(learner)
    db.flush()

    db.add(
        LearnerProfile(
            user_id=learner.id,
            target_language=Language.en,
            level=CEFRLevel.A1,
            total_xp=0,
            created_at=now,
        )
    )
    db.flush()

    # ── Published content ─────────────────────────────────────────────────────
    content = VideoContent(
        creator_id=creator.id,
        language=Language.en,
        level=CEFRLevel.A1,
        title="English for Beginners: Greetings",
        caption="Learn the most common English greetings in 30 seconds.",
        video_url=_PLACEHOLDER_VIDEO_URL,
        status=ContentStatus.draft,
        created_at=now,
    )
    db.add(content)
    db.flush()

    # ── Quiz with 3 questions ─────────────────────────────────────────────────
    quiz = Quiz(content_id=content.id, created_at=now)
    db.add(quiz)
    db.flush()

    for prompt, options, correct in _QUESTIONS:
        db.add(
            Question(
                quiz_id=quiz.id,
                prompt=prompt,
                options_json=json.dumps(options),
                correct_option_index=correct,
                created_at=now,
            )
        )
    db.flush()

    # ── Publish ───────────────────────────────────────────────────────────────
    content.status = ContentStatus.published
    content.published_at = now

    db.commit()

    print("[seed] Demo data created successfully.")
    print(f"  Creator  →  {CREATOR_EMAIL}  /  {DEMO_PASSWORD}")
    print(f"  Learner  →  {LEARNER_EMAIL}  /  {DEMO_PASSWORD}")
    print(f"  Content  →  '{content.title}' (id={content.id}, language=en, level=A1)")
    print()
    print("  Note: video_url is a placeholder. Replace with a real R2 URL for live demo.")
    print("  Start the app:  uvicorn src.app.main:app --reload")
    print("  Then open:      http://127.0.0.1:8000/")
    return True


if __name__ == "__main__":
    db = SessionLocal()
    try:
        run(db)
    finally:
        db.close()
