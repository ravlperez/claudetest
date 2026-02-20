"""
Creator routes for Language App.

API (JSON):
    POST /api/uploads/presign                  – presigned R2 PUT URL (TASK 9)
    GET  /api/creator/content                  – list the creator's content
    POST /api/creator/content                  – create a new content draft
    POST /api/creator/content/{id}/publish     – publish a draft (quiz required)
    POST /api/creator/content/{id}/quiz        – create/replace quiz (3–5 MCQ)

SSR:
    GET  /creator                              – creator dashboard (content list)
    GET  /creator/content/new                  – create-content form
    POST /creator/content                      – process create form → redirect
    GET  /creator/upload                       – video upload form (TASK 9)
    GET  /creator/content/{id}/quiz            – quiz authoring form
    GET  /creator/content/{id}                 – content detail page

Quiz rules (POST /api/creator/content/{id}/quiz):
    - Creator must own the content.
    - Exactly 3–5 questions required.
    - Each question: non-empty prompt, 2–6 non-empty options,
      correct_option_index in range [0, len(options)).
    - Replaces an existing quiz (delete + create semantics).

Publish rules (POST /api/creator/content/{id}/publish):
    - Creator must own the content.
    - video_url must be present.
    - A Quiz must exist with exactly 3–5 questions.
    - Publishing an already-published item is idempotent (200).
"""

import json
import logging
import pathlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.auth import require_creator
from src.app.csrf import generate_csrf_token, require_csrf
from src.app.database import get_db
from src.app.models import (
    CEFRLevel,
    ContentStatus,
    Language,
    Question,
    Quiz,
    User,
    VideoContent,
)
from src.app.r2 import get_bucket_name, get_public_base_url, get_r2_client

_BASE_DIR = pathlib.Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_ALLOWED_CONTENT_TYPE = "video/mp4"
_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB in bytes
_PRESIGN_TTL = 3600  # seconds (1 hour)
_VALID_LANGUAGES = [lang.value for lang in Language]
_VALID_LEVELS = [lvl.value for lvl in CEFRLevel]
_QUIZ_MIN_QUESTIONS = 3
_QUIZ_MAX_QUESTIONS = 5
_OPTION_MIN = 2
_OPTION_MAX = 6


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Pydantic schemas ───────────────────────────────────────────────────────────


class PresignRequest(BaseModel):
    content_type: str
    file_size: int  # bytes

    @field_validator("content_type")
    @classmethod
    def _content_type_valid(cls, v: str) -> str:
        if v != _ALLOWED_CONTENT_TYPE:
            raise ValueError("Only video/mp4 files are accepted")
        return v

    @field_validator("file_size")
    @classmethod
    def _file_size_valid(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("file_size must be a positive integer (bytes)")
        if v > _MAX_FILE_SIZE:
            raise ValueError(
                f"File too large: {v} bytes exceeds the 100 MB limit ({_MAX_FILE_SIZE} bytes)"
            )
        return v


class ContentCreateRequest(BaseModel):
    language: Language
    level: CEFRLevel
    title: str
    caption: str | None = None
    video_url: str

    @field_validator("title")
    @classmethod
    def _title_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty")
        return v

    @field_validator("video_url")
    @classmethod
    def _video_url_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("video_url cannot be empty")
        return v


class QuestionIn(BaseModel):
    prompt: str
    options: list[str]
    correct_option_index: int

    @field_validator("prompt")
    @classmethod
    def _prompt_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt cannot be empty")
        return v

    @field_validator("options")
    @classmethod
    def _options_valid(cls, v: list[str]) -> list[str]:
        cleaned = [opt.strip() for opt in v]
        if len(cleaned) < _OPTION_MIN:
            raise ValueError(
                f"Each question must have at least {_OPTION_MIN} options (got {len(cleaned)})"
            )
        if len(cleaned) > _OPTION_MAX:
            raise ValueError(
                f"Each question can have at most {_OPTION_MAX} options (got {len(cleaned)})"
            )
        if any(not opt for opt in cleaned):
            raise ValueError("Options cannot be empty strings")
        return cleaned

    @model_validator(mode="after")
    def _correct_index_in_range(self) -> "QuestionIn":
        if not (0 <= self.correct_option_index < len(self.options)):
            raise ValueError(
                f"correct_option_index {self.correct_option_index} is out of range "
                f"for {len(self.options)} options (valid: 0–{len(self.options) - 1})"
            )
        return self


class QuizCreateRequest(BaseModel):
    questions: list[QuestionIn]

    @field_validator("questions")
    @classmethod
    def _question_count(cls, v: list[QuestionIn]) -> list[QuestionIn]:
        if len(v) < _QUIZ_MIN_QUESTIONS:
            raise ValueError(
                f"Quiz must have at least {_QUIZ_MIN_QUESTIONS} questions (got {len(v)})"
            )
        if len(v) > _QUIZ_MAX_QUESTIONS:
            raise ValueError(
                f"Quiz must have at most {_QUIZ_MAX_QUESTIONS} questions (got {len(v)})"
            )
        return v


# ── API: uploads ───────────────────────────────────────────────────────────────


@router.post("/api/uploads/presign")
def api_presign(
    body: PresignRequest,
    current_user: User = Depends(require_creator),
) -> dict:
    """Generate a presigned R2 PUT URL for direct-to-storage video upload."""
    key = f"videos/{current_user.id}/{uuid.uuid4()}.mp4"

    try:
        client = get_r2_client()
        bucket = get_bucket_name()
        public_base = get_public_base_url()
    except KeyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Storage not configured: missing environment variable {exc}",
        )

    upload_url: str = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": body.content_type,
        },
        ExpiresIn=_PRESIGN_TTL,
    )

    public_url = f"{public_base}/{key}"

    return {
        "upload_url": upload_url,
        "public_url": public_url,
        "key": key,
        "required_headers": {"Content-Type": body.content_type},
    }


# ── API: content management ────────────────────────────────────────────────────


@router.get("/api/creator/content")
def api_list_content(
    current_user: User = Depends(require_creator),
    db: Session = Depends(get_db),
) -> dict:
    """List all VideoContent rows owned by the authenticated creator, newest first."""
    rows = (
        db.execute(
            select(VideoContent)
            .where(VideoContent.creator_id == current_user.id)
            .order_by(VideoContent.created_at.desc())
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "language": c.language,
                "level": c.level,
                "status": c.status,
                "video_url": c.video_url,
                "published_at": c.published_at.isoformat() if c.published_at else None,
                "created_at": c.created_at.isoformat(),
            }
            for c in rows
        ]
    }


@router.post("/api/creator/content", status_code=201)
def api_create_content(
    body: ContentCreateRequest,
    current_user: User = Depends(require_creator),
    db: Session = Depends(get_db),
) -> dict:
    """Create a new VideoContent draft. Returns {id, status: "draft"}."""
    content = VideoContent(
        creator_id=current_user.id,
        language=body.language,
        level=body.level,
        title=body.title,
        caption=body.caption,
        video_url=body.video_url,
        status=ContentStatus.draft,
    )
    db.add(content)
    db.commit()
    db.refresh(content)
    return {"id": content.id, "status": content.status}


@router.post("/api/creator/content/{content_id}/publish")
def api_publish_content(
    content_id: int,
    current_user: User = Depends(require_creator),
    db: Session = Depends(get_db),
) -> dict:
    """
    Transition a draft VideoContent to published.

    Preconditions (all enforced with 409 if violated):
      1. Content must have a non-empty video_url.
      2. A Quiz must be attached to the content.
      3. The quiz must have 3–5 questions.

    Ownership violation → 403.
    Already-published → idempotent 200.
    """
    content = db.get(VideoContent, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    if content.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your content")

    # Idempotent: already published
    if content.status == ContentStatus.published:
        return {
            "id": content.id,
            "status": content.status,
            "published_at": content.published_at.isoformat(),
        }

    if not content.video_url:
        raise HTTPException(
            status_code=409, detail="video_url is required to publish"
        )

    quiz = content.quiz
    if not quiz:
        raise HTTPException(
            status_code=409,
            detail="A quiz with 3–5 questions is required to publish",
        )

    q_count = len(quiz.questions)
    if q_count < _QUIZ_MIN_QUESTIONS or q_count > _QUIZ_MAX_QUESTIONS:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Quiz must have {_QUIZ_MIN_QUESTIONS}–{_QUIZ_MAX_QUESTIONS} questions "
                f"to publish (currently has {q_count})"
            ),
        )

    content.status = ContentStatus.published
    content.published_at = _utcnow()
    db.commit()
    db.refresh(content)

    logger.info(
        "creator_publish content_id=%d creator_id=%d",
        content.id, current_user.id,
    )
    return {
        "id": content.id,
        "status": content.status,
        "published_at": content.published_at.isoformat(),
    }


@router.post("/api/creator/content/{content_id}/quiz")
def api_create_quiz(
    content_id: int,
    body: QuizCreateRequest,
    current_user: User = Depends(require_creator),
    db: Session = Depends(get_db),
) -> dict:
    """
    Create (or replace) the quiz for a VideoContent.

    Replace semantics: if a quiz already exists it is deleted along with all
    its questions before the new one is created.

    Returns: {quiz_id, question_count}
    """
    content = db.get(VideoContent, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    if content.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your content")

    # Delete existing quiz + questions (replace semantics)
    existing = content.quiz
    if existing:
        for q in list(existing.questions):
            db.delete(q)
        db.flush()
        db.delete(existing)
        db.flush()

    quiz = Quiz(content_id=content_id)
    db.add(quiz)
    db.flush()  # populate quiz.id

    for q_in in body.questions:
        db.add(
            Question(
                quiz_id=quiz.id,
                prompt=q_in.prompt,
                options_json=json.dumps(q_in.options),
                correct_option_index=q_in.correct_option_index,
            )
        )

    db.commit()
    return {"quiz_id": quiz.id, "question_count": len(body.questions)}


# ── SSR pages ──────────────────────────────────────────────────────────────────


@router.get("/creator", response_class=HTMLResponse)
def page_creator_dashboard(
    request: Request,
    current_user: User = Depends(require_creator),
    db: Session = Depends(get_db),
):
    """Creator dashboard: full list of the creator's content with status badges."""
    rows = (
        db.execute(
            select(VideoContent)
            .where(VideoContent.creator_id == current_user.id)
            .order_by(VideoContent.created_at.desc())
        )
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        request, "creator_dashboard.html", {"contents": rows}
    )


# IMPORTANT: /creator/content/new must be registered BEFORE /creator/content/{id}
# so the literal path segment "new" is matched before the int path parameter.


@router.get("/creator/content/new", response_class=HTMLResponse)
def page_creator_content_new(
    request: Request,
    current_user: User = Depends(require_creator),
):
    """Render the create-content form (creator only)."""
    return templates.TemplateResponse(
        request,
        "creator_content_new.html",
        {
            "csrf_token": generate_csrf_token(),
            "languages": _VALID_LANGUAGES,
            "levels": _VALID_LEVELS,
        },
    )


@router.post("/creator/content")
def form_create_content(
    request: Request,
    title: str = Form(...),
    language: str = Form(...),
    level: str = Form(...),
    video_url: str = Form(...),
    caption: str = Form(default=""),
    _csrf: None = Depends(require_csrf),
    current_user: User = Depends(require_creator),
    db: Session = Depends(get_db),
):
    """
    Process the create-content form submission (CSRF required).
    On success: redirect 303 → /creator/content/{id}.
    """
    try:
        lang = Language(language)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid language: {language!r}")
    try:
        lvl = CEFRLevel(level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid level: {level!r}")

    title = title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    video_url = video_url.strip()
    if not video_url:
        raise HTTPException(status_code=400, detail="video_url cannot be empty")

    content = VideoContent(
        creator_id=current_user.id,
        language=lang,
        level=lvl,
        title=title,
        caption=caption.strip() or None,
        video_url=video_url,
        status=ContentStatus.draft,
    )
    db.add(content)
    db.commit()
    db.refresh(content)
    return RedirectResponse(url=f"/creator/content/{content.id}", status_code=303)


@router.get("/creator/upload", response_class=HTMLResponse)
def page_creator_upload(
    request: Request,
    current_user: User = Depends(require_creator),
):
    """Render the video upload form (creator only)."""
    return templates.TemplateResponse(request, "creator_upload.html", {})


# NOTE: /creator/content/{id}/quiz is registered BEFORE /creator/content/{id}
# — no conflict since the extra "/quiz" segment is a separate path.


@router.get("/creator/content/{content_id}/quiz", response_class=HTMLResponse)
def page_creator_quiz_form(
    content_id: int,
    request: Request,
    current_user: User = Depends(require_creator),
    db: Session = Depends(get_db),
):
    """
    Quiz authoring form for a content draft (creator only).

    If a quiz already exists, passes its current data as JSON so the
    client-side JS can pre-fill the form fields.
    """
    content = db.get(VideoContent, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    if content.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your content")

    existing_quiz: dict | None = None
    if content.quiz:
        existing_quiz = {
            "id": content.quiz.id,
            "questions": [
                {
                    "prompt": q.prompt,
                    "options": json.loads(q.options_json),
                    "correct_option_index": q.correct_option_index,
                }
                for q in content.quiz.questions
            ],
        }

    return templates.TemplateResponse(
        request,
        "creator_quiz_form.html",
        {
            "content": content,
            "existing_quiz": existing_quiz,
        },
    )


@router.get("/creator/content/{content_id}", response_class=HTMLResponse)
def page_creator_content_detail(
    content_id: int,
    request: Request,
    current_user: User = Depends(require_creator),
    db: Session = Depends(get_db),
):
    """
    Content detail page.

    Shows: title, language, level, status, video_url, caption, quiz state.
    If draft + quiz has 3–5 questions: renders a JS "Publish Now" button that calls
    POST /api/creator/content/{id}/publish.
    """
    content = db.get(VideoContent, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    if content.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your content")

    quiz = content.quiz
    q_count = len(quiz.questions) if quiz else 0
    can_publish = (
        content.status == ContentStatus.draft
        and bool(content.video_url)
        and quiz is not None
        and _QUIZ_MIN_QUESTIONS <= q_count <= _QUIZ_MAX_QUESTIONS
    )

    return templates.TemplateResponse(
        request,
        "creator_content_detail.html",
        {
            "content": content,
            "quiz": quiz,
            "q_count": q_count,
            "can_publish": can_publish,
        },
    )
