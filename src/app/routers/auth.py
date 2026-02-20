"""
Auth routes for Language App.

API (JSON):
    POST /api/auth/signup  – create account, set session cookie
    POST /api/auth/login   – authenticate, set session cookie
    GET  /api/me           – return current user

SSR (form + redirect):
    GET  /signup   – signup form
    POST /signup   – process signup form
    GET  /login    – login form
    POST /login    – process login form
    POST /logout   – clear session cookie, redirect to /login
"""

import logging
import pathlib

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.app.auth import (
    SESSION_COOKIE,
    check_login_rate_limit,
    create_session_token,
    get_current_user,
    hash_password,
    set_session_cookie,
    verify_password,
)
from src.app.csrf import generate_csrf_token, require_csrf
from src.app.database import get_db
from src.app.models import Role, User

_BASE_DIR = pathlib.Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Pydantic request/response schemas ─────────────────────────────────────────


class SignupRequest(BaseModel):
    email: str
    password: str
    role: str = "learner"

    @field_validator("email")
    @classmethod
    def _email_normalise(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("role")
    @classmethod
    def _role_valid(cls, v: str) -> str:
        if v not in ("learner", "creator"):
            raise ValueError("role must be 'learner' or 'creator'")
        return v

    @field_validator("password")
    @classmethod
    def _password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email_normalise(cls, v: str) -> str:
        return v.strip().lower()


# ── API endpoints ──────────────────────────────────────────────────────────────


@router.post("/api/auth/signup", status_code=201)
def api_signup(
    body: SignupRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """Create a new account and return a signed session cookie."""
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role=Role(body.role),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_session_token(user.id, user.role.value)
    set_session_cookie(response, token)

    return {"id": user.id, "email": user.email, "role": user.role.value}


@router.post("/api/auth/login")
def api_login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """Authenticate and return a signed session cookie."""
    client_ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(client_ip)

    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        logger.warning("auth_login_failure email=%s ip=%s", body.email, client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    logger.info(
        "auth_login_success user_id=%d email=%s role=%s",
        user.id, user.email, user.role.value,
    )
    token = create_session_token(user.id, user.role.value)
    set_session_cookie(response, token)

    return {"id": user.id, "email": user.email, "role": user.role.value}


@router.get("/api/me")
def api_me(current_user: User = Depends(get_current_user)) -> dict:
    """Return the currently authenticated user."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role.value,
    }


# ── SSR pages ──────────────────────────────────────────────────────────────────


@router.get("/signup", response_class=HTMLResponse)
def page_signup(request: Request):
    return templates.TemplateResponse(
        request, "signup.html", {"error": None, "csrf_token": generate_csrf_token()}
    )


@router.post("/signup", response_class=HTMLResponse)
def page_signup_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(default="learner"),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    email = email.strip().lower()
    error: str | None = None

    if len(password) < 8:
        error = "Password must be at least 8 characters."
    elif role not in ("learner", "creator"):
        error = "Invalid role selected."
    else:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            error = "Email already registered."
        else:
            try:
                user = User(
                    email=email,
                    password_hash=hash_password(password),
                    role=Role(role),
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                token = create_session_token(user.id, user.role.value)
                redirect = RedirectResponse(url="/", status_code=303)
                set_session_cookie(redirect, token)
                return redirect
            except IntegrityError:
                db.rollback()
                error = "Email already registered."

    return templates.TemplateResponse(
        request,
        "signup.html",
        {"error": error, "csrf_token": generate_csrf_token()},
        status_code=400,
    )


@router.get("/login", response_class=HTMLResponse)
def page_login(request: Request):
    return templates.TemplateResponse(
        request, "login.html", {"error": None, "csrf_token": generate_csrf_token()}
    )


@router.post("/login", response_class=HTMLResponse)
def page_login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    email = email.strip().lower()
    client_ip = request.client.host if request.client else "unknown"

    try:
        check_login_rate_limit(client_ip)
    except HTTPException:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Too many login attempts. Please wait.", "csrf_token": generate_csrf_token()},
            status_code=429,
        )

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid email or password.", "csrf_token": generate_csrf_token()},
            status_code=401,
        )

    token = create_session_token(user.id, user.role.value)
    redirect = RedirectResponse(url="/", status_code=303)
    set_session_cookie(redirect, token)
    return redirect


@router.post("/logout")
def logout(_csrf: None = Depends(require_csrf)):
    redirect = RedirectResponse(url="/login", status_code=303)
    redirect.delete_cookie(key=SESSION_COOKIE)
    return redirect
