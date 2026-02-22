import pathlib

from fastapi.templating import Jinja2Templates

from src.app.auth import SESSION_COOKIE, decode_session_token

_BASE_DIR = pathlib.Path(__file__).parent

templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


def _get_user_role(request) -> str | None:
    """Return 'learner', 'creator', or None from the session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    data = decode_session_token(token)
    return data.get("role") if data else None


templates.env.globals["user_role"] = _get_user_role
