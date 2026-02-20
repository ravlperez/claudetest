"""
Authentication utilities for Language App.

Provides:
- Password hashing / verification (bcrypt via passlib)
- Signed session token creation / decoding (itsdangerous)
- FastAPI dependencies: get_current_user
- In-memory per-IP login rate limiter
"""

import threading
from collections import defaultdict
from datetime import datetime, timezone

import bcrypt
from fastapi import Cookie, Depends, HTTPException
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import Session

from src.app.config import IS_PROD, SECRET_KEY
from src.app.database import get_db
from src.app.models import User

# ── Password hashing ──────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Session tokens ────────────────────────────────────────────────────────────

_SESSION_SALT = "session-v1"
SESSION_COOKIE = "session"
COOKIE_MAX_AGE = 14 * 24 * 60 * 60  # 14 days


def create_session_token(user_id: int, role: str) -> str:
    s = URLSafeSerializer(SECRET_KEY, salt=_SESSION_SALT)
    return s.dumps({"user_id": user_id, "role": role})


def decode_session_token(token: str) -> dict | None:
    s = URLSafeSerializer(SECRET_KEY, salt=_SESSION_SALT)
    try:
        return s.loads(token)
    except BadSignature:
        return None


def set_session_cookie(response, token: str) -> None:
    """Attach a signed session cookie to any Response (or RedirectResponse)."""
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=IS_PROD,
        max_age=COOKIE_MAX_AGE,
    )


# ── Current-user dependency ───────────────────────────────────────────────────


def get_current_user(
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    """Return the authenticated User or raise 401."""
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    data = decode_session_token(session)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid session")
    user = db.get(User, data["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── Rate limiter ──────────────────────────────────────────────────────────────

_RATE_WINDOW = 60  # seconds
_RATE_MAX = 5  # max login attempts per window per IP

_login_attempts: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()


def check_login_rate_limit(ip: str) -> None:
    """Raise HTTP 429 if the IP has exceeded the login rate limit."""
    now = datetime.now(timezone.utc).timestamp()
    with _rate_lock:
        attempts = [t for t in _login_attempts[ip] if now - t < _RATE_WINDOW]
        attempts.append(now)
        _login_attempts[ip] = attempts
        if len(attempts) > _RATE_MAX:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Please wait a minute.",
            )


def _reset_rate_limits() -> None:
    """Clear all recorded login attempts. Used only in tests."""
    with _rate_lock:
        _login_attempts.clear()
