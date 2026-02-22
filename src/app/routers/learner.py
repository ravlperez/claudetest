"""
Learner onboarding, feed, and profile routes.

API (JSON):
    POST /api/learner/profile  – create or update learner profile (learner only)
    GET  /api/learner/profile  – fetch learner profile           (learner only)
    GET  /api/feed             – paginated published-content feed (learner only)
    GET  /api/content/{id}/quiz – fetch quiz for published content (learner only)

SSR:
    GET  /onboarding  – onboarding form                          (learner only)
    POST /onboarding  – save profile, redirect to /feed          (learner only)
    GET  /feed        – feed page; redirects to /onboarding if profile missing

Pagination strategy (GET /api/feed):
    Cursor encodes (published_at, id) as a base64-URL JSON string.
    Query: WHERE language=? AND level=? AND status='published'
             AND (published_at < cur.published_at
                  OR (published_at = cur.published_at AND id < cur.id))
    ORDER BY published_at DESC, id DESC
    LIMIT min(limit, 50) + 1   ← extra row to detect whether a next page exists
"""

import base64
import json
import logging

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from src.app.auth import get_current_user, require_learner
from src.app.csrf import generate_csrf_token, require_csrf
from src.app.database import get_db
from src.app.models import (
    CEFRLevel,
    ContentStatus,
    Language,
    LearnerProfile,
    Quiz,
    QuizAttempt,
    Streak,
    User,
    VideoContent,
    XPEvent,
    XPReason,
)

from src.app.shared_templates import templates

router = APIRouter()
logger = logging.getLogger(__name__)

_VALID_LANGUAGES = ("en", "es", "fr")
_VALID_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
_FEED_DEFAULT_LIMIT = 10
_FEED_MAX_LIMIT = 50

_XP_BASE = 30
_XP_BONUS_80 = 10
_XP_BONUS_100 = 20


# ── Attempt helpers (overridable for tests) ───────────────────────────────────


def _current_utc_date() -> str:
    """Return today's UTC date as YYYY-MM-DD. Monkeypatchable in tests."""
    return datetime.now(timezone.utc).date().isoformat()


def _calc_xp(score_percent: int) -> int:
    """Return XP amount for a given score percent per SPEC 6.2 rules."""
    xp = _XP_BASE
    if score_percent >= 80:
        xp += _XP_BONUS_80
    if score_percent == 100:
        xp += _XP_BONUS_100
    return xp


def _update_streak_inplace(streak: Streak, today_str: str) -> None:
    """Update streak row in place given today's UTC date string (YYYY-MM-DD)."""
    yesterday_str = (date.fromisoformat(today_str) - timedelta(days=1)).isoformat()
    if streak.last_active_date_utc == today_str:
        # Already active today — no change
        pass
    elif streak.last_active_date_utc == yesterday_str:
        # Consecutive day — extend streak
        streak.current_streak_days += 1
        streak.last_active_date_utc = today_str
    else:
        # First activity ever, or missed one or more days — reset to 1
        streak.current_streak_days = 1
        streak.last_active_date_utc = today_str


# ── Cursor helpers ────────────────────────────────────────────────────────────


def _encode_cursor(published_at: datetime, item_id: int) -> str:
    payload = {"published_at": published_at.isoformat(), "id": item_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, int] | None:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(payload["published_at"]), int(payload["id"])
    except Exception:
        return None


# ── Feed query helper ─────────────────────────────────────────────────────────


def _get_feed_items(
    db: Session,
    language: Language,
    level: CEFRLevel,
    cursor: str | None,
    limit: int,
) -> tuple[list[VideoContent], str | None]:
    """Return (items, next_cursor) for one page of the feed."""
    limit = min(max(1, limit), _FEED_MAX_LIMIT)

    q = (
        select(VideoContent)
        .where(
            VideoContent.language == language,
            VideoContent.level == level,
            VideoContent.status == ContentStatus.published,
        )
        .order_by(VideoContent.published_at.desc(), VideoContent.id.desc())
        .limit(limit + 1)  # fetch one extra to detect next page
    )

    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            pub_at, item_id = decoded
            q = q.where(
                or_(
                    VideoContent.published_at < pub_at,
                    and_(
                        VideoContent.published_at == pub_at,
                        VideoContent.id < item_id,
                    ),
                )
            )

    rows = list(db.execute(q).scalars().all())

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        if last.published_at is not None:
            next_cursor = _encode_cursor(last.published_at, last.id)

    return rows, next_cursor


def _video_to_dict(v: VideoContent) -> dict:
    return {
        "id": v.id,
        "creator_id": v.creator_id,
        "language": v.language.value,
        "level": v.level.value,
        "title": v.title,
        "caption": v.caption,
        "video_url": v.video_url,
        "thumbnail_url": v.thumbnail_url,
        "status": v.status.value,
        "published_at": v.published_at.isoformat() + "Z" if v.published_at else None,
    }


# ── Pydantic schema ───────────────────────────────────────────────────────────


class ProfileRequest(BaseModel):
    target_language: str
    level: str

    @field_validator("target_language")
    @classmethod
    def _lang_valid(cls, v: str) -> str:
        if v not in _VALID_LANGUAGES:
            raise ValueError(f"target_language must be one of: {', '.join(_VALID_LANGUAGES)}")
        return v

    @field_validator("level")
    @classmethod
    def _level_valid(cls, v: str) -> str:
        if v not in _VALID_LEVELS:
            raise ValueError(f"level must be one of: {', '.join(_VALID_LEVELS)}")
        return v


class AnswerIn(BaseModel):
    question_id: int
    selected_index: int

    @field_validator("selected_index")
    @classmethod
    def _index_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("selected_index must be >= 0")
        return v


class AttemptRequest(BaseModel):
    answers: list[AnswerIn]

    @field_validator("answers")
    @classmethod
    def _answers_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("answers must not be empty")
        return v


# ── API endpoints ──────────────────────────────────────────────────────────────


@router.post("/api/learner/profile", status_code=200)
def api_create_or_update_profile(
    body: ProfileRequest,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> dict:
    """Create or update the learner's language/level profile."""
    profile = db.get(LearnerProfile, current_user.id)
    if profile:
        profile.target_language = Language(body.target_language)
        profile.level = CEFRLevel(body.level)
    else:
        profile = LearnerProfile(
            user_id=current_user.id,
            target_language=Language(body.target_language),
            level=CEFRLevel(body.level),
        )
        db.add(profile)
    db.commit()
    db.refresh(profile)
    return {
        "user_id": profile.user_id,
        "target_language": profile.target_language.value,
        "level": profile.level.value,
        "total_xp": profile.total_xp,
    }


@router.get("/api/learner/profile")
def api_get_profile(
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> dict:
    """Return the learner's profile or 404 if onboarding has not been completed."""
    profile = db.get(LearnerProfile, current_user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Complete onboarding first.")
    return {
        "user_id": profile.user_id,
        "target_language": profile.target_language.value,
        "level": profile.level.value,
        "total_xp": profile.total_xp,
    }


@router.get("/api/feed")
def api_feed(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_FEED_DEFAULT_LIMIT, ge=1, le=_FEED_MAX_LIMIT),
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> dict:
    """
    Return a cursor-paginated list of published videos matching the learner's
    language and CEFR level.

    Errors:
        401 – not authenticated
        403 – caller is not a learner
        412 – learner has not completed onboarding (no profile)
    """
    profile = db.get(LearnerProfile, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=412,
            detail="Profile required. Complete onboarding at /onboarding first.",
        )

    items, next_cursor = _get_feed_items(
        db, profile.target_language, profile.level, cursor, limit
    )
    return {
        "items": [_video_to_dict(v) for v in items],
        "next_cursor": next_cursor,
    }


@router.get("/api/content/{content_id}/quiz")
def api_get_quiz(
    content_id: int,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> dict:
    """
    Return the quiz for a published VideoContent.

    Errors:
        401 – not authenticated
        403 – caller is not a learner
        404 – content not found, or content exists but has no quiz
        409 – content exists but is not published (still a draft)

    Note: correct_option_index is intentionally omitted from the response
    to prevent leaking answers to the client.
    """
    content = db.get(VideoContent, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    if content.status != ContentStatus.published:
        raise HTTPException(status_code=409, detail="Content is not published")

    quiz = content.quiz
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found for this content")

    return {
        "content": {
            "id": content.id,
            "title": content.title,
            "video_url": content.video_url,
        },
        "quiz": {
            "id": quiz.id,
            "questions": [
                {
                    "id": q.id,
                    "type": "multiple_choice",
                    "prompt": q.prompt,
                    "options": json.loads(q.options_json),
                    # correct_option_index intentionally omitted (server-side secret)
                }
                for q in quiz.questions
            ],
        },
    }


@router.get("/api/progress")
def api_progress(
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> dict:
    """
    Return the learner's total XP, current streak, and last 10 attempts (newest first).

    Errors:
        401 – not authenticated
        403 – caller is not a learner
    """
    profile = db.get(LearnerProfile, current_user.id)
    streak = db.get(Streak, current_user.id)

    recent = list(
        db.execute(
            select(QuizAttempt)
            .where(QuizAttempt.user_id == current_user.id)
            .order_by(QuizAttempt.completed_at.desc())
            .limit(10)
        ).scalars()
    )

    return {
        "total_xp": profile.total_xp if profile else 0,
        "current_streak_days": streak.current_streak_days if streak else 0,
        "last_active_date_utc": streak.last_active_date_utc if streak else None,
        "recent_attempts": [
            {
                "attempt_id": a.id,
                "content_id": a.content_id,
                "score_percent": a.score_percent,
                "xp_awarded": a.xp_awarded,
                "completed_at": a.completed_at.isoformat() + "Z",
            }
            for a in recent
        ],
    }


@router.post("/api/content/{content_id}/attempt", status_code=201)
def api_submit_attempt(
    content_id: int,
    body: AttemptRequest,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
) -> dict:
    """
    Submit quiz answers for published content. Scores the attempt, awards XP
    (at most once per content per UTC day), and updates the learner's streak.

    Errors:
        401 – not authenticated
        403 – caller is not a learner
        404 – content or quiz not found
        409 – content is a draft
        422 – invalid answers (wrong count, unknown question_id, out-of-range index)
    """
    content = db.get(VideoContent, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    if content.status != ContentStatus.published:
        raise HTTPException(status_code=409, detail="Content is not published")

    quiz = content.quiz
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    questions = quiz.questions
    question_map = {q.id: q for q in questions}

    # Validate answer count and question IDs
    if len(body.answers) != len(questions):
        raise HTTPException(
            status_code=422,
            detail=f"Expected {len(questions)} answers, got {len(body.answers)}",
        )
    for ans in body.answers:
        if ans.question_id not in question_map:
            raise HTTPException(
                status_code=422, detail=f"Unknown question_id: {ans.question_id}"
            )
        options = json.loads(question_map[ans.question_id].options_json)
        if ans.selected_index >= len(options):
            raise HTTPException(
                status_code=422,
                detail=f"selected_index {ans.selected_index} out of range for question {ans.question_id}",
            )

    # Score
    correct_count = sum(
        1
        for ans in body.answers
        if question_map[ans.question_id].correct_option_index == ans.selected_index
    )
    total_questions = len(questions)
    score_percent = int((correct_count / total_questions) * 100)

    # XP: awarded at most once per content per UTC day
    today_str = _current_utc_date()
    already_earned = db.execute(
        select(QuizAttempt).where(
            QuizAttempt.user_id == current_user.id,
            QuizAttempt.content_id == content_id,
            QuizAttempt.completed_date_utc == today_str,
            QuizAttempt.xp_awarded > 0,
        )
    ).scalars().first()
    xp_awarded = 0 if already_earned else _calc_xp(score_percent)

    # Create attempt record
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    attempt = QuizAttempt(
        user_id=current_user.id,
        content_id=content_id,
        quiz_id=quiz.id,
        score_percent=score_percent,
        correct_count=correct_count,
        total_questions=total_questions,
        xp_awarded=xp_awarded,
        completed_at=now,
        completed_date_utc=today_str,
    )
    db.add(attempt)

    # Update total_xp and create XPEvent when XP is awarded
    if xp_awarded > 0:
        profile = db.get(LearnerProfile, current_user.id)
        if profile:
            profile.total_xp += xp_awarded
        db.add(
            XPEvent(
                user_id=current_user.id,
                content_id=content_id,
                reason=XPReason.quiz_completed,
                xp_amount=xp_awarded,
                created_date_utc=today_str,
            )
        )

    # Update streak
    streak = db.get(Streak, current_user.id)
    if not streak:
        streak = Streak(user_id=current_user.id)
        db.add(streak)
    _update_streak_inplace(streak, today_str)

    db.commit()
    db.refresh(attempt)
    db.refresh(streak)

    logger.info(
        "learner_attempt_submitted user_id=%d content_id=%d score=%d xp_awarded=%d",
        current_user.id, content_id, score_percent, xp_awarded,
    )
    return {
        "attempt_id": attempt.id,
        "score_percent": score_percent,
        "correct_count": correct_count,
        "total_questions": total_questions,
        "xp_awarded": xp_awarded,
        "streak": {
            "current_streak_days": streak.current_streak_days,
            "last_active_date_utc": streak.last_active_date_utc,
        },
    }


# ── SSR pages ──────────────────────────────────────────────────────────────────


@router.get("/onboarding", response_class=HTMLResponse)
def page_onboarding(
    request: Request,
    current_user: User = Depends(require_learner),
):
    return templates.TemplateResponse(
        request,
        "onboarding.html",
        {"error": None, "csrf_token": generate_csrf_token()},
    )


@router.post("/onboarding", response_class=HTMLResponse)
def page_onboarding_submit(
    request: Request,
    target_language: str = Form(...),
    level: str = Form(...),
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    error: str | None = None

    if target_language not in _VALID_LANGUAGES:
        error = "Please select a valid target language."
    elif level not in _VALID_LEVELS:
        error = "Please select a valid CEFR level."
    else:
        profile = db.get(LearnerProfile, current_user.id)
        if profile:
            profile.target_language = Language(target_language)
            profile.level = CEFRLevel(level)
        else:
            profile = LearnerProfile(
                user_id=current_user.id,
                target_language=Language(target_language),
                level=CEFRLevel(level),
            )
            db.add(profile)
        db.commit()
        return RedirectResponse(url="/feed", status_code=303)

    return templates.TemplateResponse(
        request,
        "onboarding.html",
        {"error": error, "csrf_token": generate_csrf_token()},
        status_code=400,
    )


@router.get("/feed", response_class=HTMLResponse)
def page_feed(
    request: Request,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
):
    """
    Feed page — learner only.
    Redirects to /onboarding if the learner has not completed their profile.
    First page of matching published videos is embedded in the HTML; further
    pages are loaded via JS calling GET /api/feed.
    """
    profile = db.get(LearnerProfile, current_user.id)
    if not profile:
        return RedirectResponse(url="/onboarding", status_code=303)

    items, next_cursor = _get_feed_items(
        db, profile.target_language, profile.level, None, _FEED_DEFAULT_LIMIT
    )
    return templates.TemplateResponse(
        request,
        "feed.html",
        {
            "user": current_user,
            "profile": profile,
            "items": items,
            "next_cursor": next_cursor,
        },
    )


@router.get("/content/{content_id}/quiz", response_class=HTMLResponse)
def page_quiz(
    content_id: int,
    request: Request,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
):
    """
    SSR quiz page — shows the video and quiz form for a published content item.
    Learner only; submits answers via JS to POST /api/content/{id}/attempt.
    """
    content = db.get(VideoContent, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    if content.status != ContentStatus.published:
        raise HTTPException(status_code=409, detail="Content is not published")

    quiz = content.quiz
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    questions_data = [
        {
            "id": q.id,
            "prompt": q.prompt,
            "options": json.loads(q.options_json),
        }
        for q in quiz.questions
    ]
    return templates.TemplateResponse(
        request,
        "quiz_page.html",
        {"content": content, "quiz": quiz, "questions": questions_data},
    )


@router.get("/attempts/{attempt_id}", response_class=HTMLResponse)
def page_attempt_result(
    attempt_id: int,
    request: Request,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
):
    """
    SSR results page showing score, XP awarded, and streak for an attempt.
    Only the attempt owner may view it.
    """
    attempt = db.get(QuizAttempt, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if attempt.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your attempt")

    content = db.get(VideoContent, attempt.content_id)
    streak = db.get(Streak, current_user.id)

    return templates.TemplateResponse(
        request,
        "attempt_result.html",
        {"attempt": attempt, "content": content, "streak": streak},
    )


@router.get("/progress", response_class=HTMLResponse)
def page_progress(
    request: Request,
    current_user: User = Depends(require_learner),
    db: Session = Depends(get_db),
):
    """
    SSR progress dashboard — total XP, streak, and recent attempts. Learner only.
    """
    profile = db.get(LearnerProfile, current_user.id)
    streak = db.get(Streak, current_user.id)

    recent = list(
        db.execute(
            select(QuizAttempt)
            .where(QuizAttempt.user_id == current_user.id)
            .order_by(QuizAttempt.completed_at.desc())
            .limit(10)
        ).scalars()
    )

    # Enrich with content titles for display
    enriched = []
    for a in recent:
        content = db.get(VideoContent, a.content_id)
        enriched.append({"attempt": a, "content": content})

    return templates.TemplateResponse(
        request,
        "progress.html",
        {
            "total_xp": profile.total_xp if profile else 0,
            "streak": streak,
            "enriched_attempts": enriched,
        },
    )
