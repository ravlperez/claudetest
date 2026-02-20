"""
Learner onboarding, feed, and profile routes.

API (JSON):
    POST /api/learner/profile  – create or update learner profile (learner only)
    GET  /api/learner/profile  – fetch learner profile           (learner only)
    GET  /api/feed             – paginated published-content feed (learner only)

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
import pathlib
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
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
    User,
    VideoContent,
)

_BASE_DIR = pathlib.Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

router = APIRouter()

_VALID_LANGUAGES = ("en", "es", "fr")
_VALID_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
_FEED_DEFAULT_LIMIT = 10
_FEED_MAX_LIMIT = 50


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
