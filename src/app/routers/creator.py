"""
Creator routes for Language App.

API (JSON):
    POST /api/uploads/presign  – generate a presigned R2 PUT URL (creator only)

SSR:
    GET /creator/upload  – video upload form page (creator only)

Presign flow:
    1. Creator POSTs {content_type, file_size} to /api/uploads/presign.
    2. Server validates content_type == "video/mp4" and file_size <= 100 MB.
    3. Server generates a unique object key: videos/{creator_id}/{uuid}.mp4
    4. Server calls R2 (S3-compatible) to generate a presigned PUT URL valid
       for 1 hour.
    5. Response: {upload_url, public_url, key, required_headers}.
    6. Browser PUTs the file directly to upload_url with required_headers.
    7. On success, public_url is the permanent playable URL to store on VideoContent.
"""

import pathlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from src.app.auth import require_creator
from src.app.models import User
from src.app.r2 import get_bucket_name, get_public_base_url, get_r2_client

_BASE_DIR = pathlib.Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

router = APIRouter()

_ALLOWED_CONTENT_TYPE = "video/mp4"
_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB in bytes
_PRESIGN_TTL = 3600  # seconds (1 hour)


# ── Pydantic schema ───────────────────────────────────────────────────────────


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


# ── API endpoints ──────────────────────────────────────────────────────────────


@router.post("/api/uploads/presign")
def api_presign(
    body: PresignRequest,
    current_user: User = Depends(require_creator),
) -> dict:
    """
    Generate a presigned R2 PUT URL for direct-to-storage video upload.

    Returns:
        upload_url      – presigned PUT URL (expires in 1 hour)
        public_url      – permanent public URL of the uploaded object
        key             – storage object key (videos/{creator_id}/{uuid}.mp4)
        required_headers– headers the browser must include in the PUT request
    """
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


# ── SSR pages ──────────────────────────────────────────────────────────────────


@router.get("/creator/upload", response_class=HTMLResponse)
def page_creator_upload(
    request: Request,
    current_user: User = Depends(require_creator),
):
    """Render the video upload form (creator only)."""
    return templates.TemplateResponse(request, "creator_upload.html", {})
