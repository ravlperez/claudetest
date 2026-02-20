"""
Learner onboarding and feed routes.

API (JSON):
    POST /api/learner/profile  – create or update learner profile (learner only)
    GET  /api/learner/profile  – fetch learner profile          (learner only)

SSR:
    GET  /onboarding  – onboarding form                         (learner only)
    POST /onboarding  – save profile, redirect to /feed         (learner only)
    GET  /feed        – feed stub; redirects to /onboarding if profile missing
"""

import pathlib

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from src.app.auth import get_current_user, require_learner
from src.app.csrf import generate_csrf_token, require_csrf
from src.app.database import get_db
from src.app.models import CEFRLevel, Language, LearnerProfile, User

_BASE_DIR = pathlib.Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

router = APIRouter()

_VALID_LANGUAGES = ("en", "es", "fr")
_VALID_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


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
    """
    profile = db.get(LearnerProfile, current_user.id)
    if not profile:
        return RedirectResponse(url="/onboarding", status_code=303)
    return templates.TemplateResponse(
        request,
        "feed.html",
        {"user": current_user, "profile": profile},
    )
