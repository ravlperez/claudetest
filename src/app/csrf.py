"""
CSRF protection for Language App.

Strategy: signed synchronizer token pattern using itsdangerous.
  - GET routes generate a token and pass it to templates.
  - SSR POST forms embed the token as a hidden field.
  - The require_csrf FastAPI dependency validates the field on every POST.
  - JSON API routes (/api/*) are exempt — they are called by JS with JSON bodies,
    not by cross-site forms.

Why this is safe:
  - Tokens are server-signed (tamper-proof).
  - Tokens expire after CSRF_MAX_AGE seconds.
  - A cross-origin attacker cannot read the HTML response to extract the token
    (blocked by Same-Origin Policy), so they cannot forge a valid form POST.
"""

from fastapi import Form, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.app.config import SECRET_KEY

_CSRF_SALT = "csrf-v1"
_CSRF_MAX_AGE = 3600  # seconds — token valid for 1 hour


def generate_csrf_token() -> str:
    """Return a fresh server-signed CSRF token to embed in a form."""
    s = URLSafeTimedSerializer(SECRET_KEY, salt=_CSRF_SALT)
    return s.dumps("csrf")


def validate_csrf_token(token: str) -> None:
    """
    Raise HTTP 403 if *token* is absent, tampered, or expired.

    Called from require_csrf (FastAPI dependency) and directly in tests.
    """
    if not token:
        raise HTTPException(status_code=403, detail="CSRF token missing")
    s = URLSafeTimedSerializer(SECRET_KEY, salt=_CSRF_SALT)
    try:
        s.loads(token, max_age=_CSRF_MAX_AGE)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=403, detail="Invalid or expired CSRF token")


def require_csrf(csrf_token: str = Form(default="")) -> None:
    """
    FastAPI dependency for SSR POST routes.

    Reads the hidden ``csrf_token`` field from form data and raises 403
    if it is missing or invalid.  Add as ``Depends(require_csrf)`` to any
    state-changing SSR endpoint.
    """
    validate_csrf_token(csrf_token)
