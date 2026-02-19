"""
ORM models for Language App MVP.

Tables (9):
    User             – both learners and creators; role is mutually exclusive
    LearnerProfile   – language/level preferences and cumulative XP
    CreatorProfile   – public display name / bio
    VideoContent     – creator-uploaded video; status: draft → published
    Quiz             – one quiz per VideoContent (unique constraint)
    Question         – multiple-choice question belonging to a Quiz
    QuizAttempt      – learner's scored attempt; XP awarded at most once/UTC day
    XPEvent          – individual XP award record (audit log)
    Streak           – learner's current daily streak counter (UTC dates)
"""

import enum
from datetime import datetime, timezone


def _utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (timezone info stripped).

    Replaces the deprecated datetime.utcnow() while keeping stored values
    consistent (naive UTC datetimes in SQLite).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────


class Role(str, enum.Enum):
    learner = "learner"
    creator = "creator"


class Language(str, enum.Enum):
    en = "en"
    es = "es"
    fr = "fr"


class CEFRLevel(str, enum.Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class ContentStatus(str, enum.Enum):
    draft = "draft"
    published = "published"


class QuestionType(str, enum.Enum):
    multiple_choice = "multiple_choice"


class XPReason(str, enum.Enum):
    quiz_completed = "quiz_completed"
    streak_bonus = "streak_bonus"


# ── Models ────────────────────────────────────────────────────────────────────


class User(Base):
    """Auth identity for both learners and creators (role is mutually exclusive)."""

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    # Relationships
    learner_profile: Mapped["LearnerProfile"] = relationship(
        back_populates="user", uselist=False
    )
    creator_profile: Mapped["CreatorProfile"] = relationship(
        back_populates="user", uselist=False
    )
    video_contents: Mapped[list["VideoContent"]] = relationship(
        back_populates="creator"
    )
    quiz_attempts: Mapped[list["QuizAttempt"]] = relationship(back_populates="user")
    xp_events: Mapped[list["XPEvent"]] = relationship(back_populates="user")
    streak: Mapped["Streak"] = relationship(back_populates="user", uselist=False)


class LearnerProfile(Base):
    """Target language, CEFR level, and cumulative XP for a learner."""

    __tablename__ = "learner_profile"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), primary_key=True
    )
    target_language: Mapped[Language] = mapped_column(
        Enum(Language), nullable=False, index=True
    )
    level: Mapped[CEFRLevel] = mapped_column(
        Enum(CEFRLevel), nullable=False, index=True
    )
    total_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    user: Mapped["User"] = relationship(back_populates="learner_profile")


class CreatorProfile(Base):
    """Public-facing name and bio for a creator."""

    __tablename__ = "creator_profile"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    user: Mapped["User"] = relationship(back_populates="creator_profile")


class VideoContent(Base):
    """Creator-uploaded video with metadata; lifecycle: draft → published."""

    __tablename__ = "video_content"
    __table_args__ = (
        # Composite index for the feed query:
        # WHERE language=? AND level=? AND status='published' ORDER BY published_at DESC
        Index("ix_video_content_feed", "language", "level", "status", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), nullable=False, index=True
    )
    language: Mapped[Language] = mapped_column(
        Enum(Language), nullable=False, index=True
    )
    level: Mapped[CEFRLevel] = mapped_column(
        Enum(CEFRLevel), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus),
        nullable=False,
        default=ContentStatus.draft,
        index=True,
    )
    video_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    creator: Mapped["User"] = relationship(back_populates="video_contents")
    quiz: Mapped["Quiz"] = relationship(back_populates="content", uselist=False)
    quiz_attempts: Mapped[list["QuizAttempt"]] = relationship(
        back_populates="content"
    )
    xp_events: Mapped[list["XPEvent"]] = relationship(back_populates="content")


class Quiz(Base):
    """Exactly one quiz per VideoContent (content_id is unique)."""

    __tablename__ = "quiz"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("video_content.id"), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    content: Mapped["VideoContent"] = relationship(back_populates="quiz")
    questions: Mapped[list["Question"]] = relationship(back_populates="quiz")
    attempts: Mapped[list["QuizAttempt"]] = relationship(back_populates="quiz")


class Question(Base):
    """A single multiple-choice question; options stored as JSON in TEXT column."""

    __tablename__ = "question"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quiz.id"), nullable=False, index=True
    )
    # SQL column named "type" per SPEC; Python attribute named question_type to
    # avoid shadowing Python's built-in type().
    question_type: Mapped[QuestionType] = mapped_column(
        "type",
        Enum(QuestionType),
        nullable=False,
        default=QuestionType.multiple_choice,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON-encoded list of option strings
    correct_option_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")


class QuizAttempt(Base):
    """Learner's scored quiz attempt; XP awarded at most once per content per UTC day."""

    __tablename__ = "quiz_attempt"
    __table_args__ = (
        # Fast lookup: "has this user already earned XP for this content today?"
        Index(
            "ix_quiz_attempt_xp_enforce", "user_id", "content_id", "completed_date_utc"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), nullable=False, index=True
    )
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("video_content.id"), nullable=False, index=True
    )
    quiz_id: Mapped[int] = mapped_column(Integer, ForeignKey("quiz.id"), nullable=False)
    score_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    xp_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    completed_date_utc: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True
    )  # YYYY-MM-DD (UTC)

    user: Mapped["User"] = relationship(back_populates="quiz_attempts")
    content: Mapped["VideoContent"] = relationship(back_populates="quiz_attempts")
    quiz: Mapped["Quiz"] = relationship(back_populates="attempts")


class XPEvent(Base):
    """Individual XP award record; serves as an audit trail for XP history."""

    __tablename__ = "xp_event"
    __table_args__ = (
        Index("ix_xp_event_user_date", "user_id", "created_date_utc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), nullable=False, index=True
    )
    content_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("video_content.id"), nullable=True
    )
    reason: Mapped[XPReason] = mapped_column(Enum(XPReason), nullable=False)
    xp_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    created_date_utc: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True
    )  # YYYY-MM-DD (UTC)

    user: Mapped["User"] = relationship(back_populates="xp_events")
    content: Mapped["VideoContent"] = relationship(back_populates="xp_events")


class Streak(Base):
    """Learner's daily quiz streak; all dates stored as YYYY-MM-DD UTC strings."""

    __tablename__ = "streak"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), primary_key=True
    )
    current_streak_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_active_date_utc: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # YYYY-MM-DD (UTC); null means no activity yet

    user: Mapped["User"] = relationship(back_populates="streak")
