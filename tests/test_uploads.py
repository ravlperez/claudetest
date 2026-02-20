"""
Acceptance criteria for TASK 9:
- Creator can request a presigned URL (mocked R2)
- Response includes upload_url, public_url (correct pattern), required_headers
- Invalid content_type → 422
- File too large → 422
- Learner blocked → 403
- Unauthenticated → 401
- R2 not configured (missing env vars) → 503
- Upload page renders for creator; blocked for learner
"""

from unittest.mock import MagicMock, patch

import pytest

# ── Shared constants ──────────────────────────────────────────────────────────

_PRESIGN_URL = "https://r2-presigned.example.com/upload?sig=abc"
_PUBLIC_BASE = "https://pub.example.com"
_BUCKET = "test-bucket"

_CREATOR = {"email": "creator@example.com", "password": "password123", "role": "creator"}
_LEARNER = {"email": "learner@example.com", "password": "password123", "role": "learner"}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _as_creator(client):
    client.post("/api/auth/signup", json=_CREATOR)


def _as_learner(client):
    client.post("/api/auth/signup", json=_LEARNER)


def _valid_payload(content_type: str = "video/mp4", file_size: int = 5 * 1024 * 1024) -> dict:
    return {"content_type": content_type, "file_size": file_size}


def _mock_r2():
    """
    Return a tuple of three patch context managers that fake the R2 helpers.
    Usage:
        with _mock_r2() as (mock_client, _, _):
            ...
    """
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = _PRESIGN_URL
    p_factory = patch("src.app.routers.creator.get_r2_client", return_value=mock_client)
    p_bucket = patch("src.app.routers.creator.get_bucket_name", return_value=_BUCKET)
    p_public = patch("src.app.routers.creator.get_public_base_url", return_value=_PUBLIC_BASE)
    return p_factory, p_bucket, p_public


# ── POST /api/uploads/presign — auth ──────────────────────────────────────────


def test_presign_unauthenticated_returns_401(client):
    r = client.post("/api/uploads/presign", json=_valid_payload())
    assert r.status_code == 401


def test_presign_learner_returns_403(client):
    _as_learner(client)
    r = client.post("/api/uploads/presign", json=_valid_payload())
    assert r.status_code == 403


# ── POST /api/uploads/presign — validation ────────────────────────────────────


def test_presign_wrong_content_type_returns_422(client):
    _as_creator(client)
    r = client.post("/api/uploads/presign", json=_valid_payload(content_type="video/webm"))
    assert r.status_code == 422


def test_presign_non_video_content_type_returns_422(client):
    _as_creator(client)
    r = client.post("/api/uploads/presign", json=_valid_payload(content_type="application/octet-stream"))
    assert r.status_code == 422


def test_presign_file_too_large_returns_422(client):
    _as_creator(client)
    too_large = 100 * 1024 * 1024 + 1  # 100 MB + 1 byte
    r = client.post("/api/uploads/presign", json=_valid_payload(file_size=too_large))
    assert r.status_code == 422


def test_presign_file_size_zero_returns_422(client):
    _as_creator(client)
    r = client.post("/api/uploads/presign", json=_valid_payload(file_size=0))
    assert r.status_code == 422


def test_presign_negative_file_size_returns_422(client):
    _as_creator(client)
    r = client.post("/api/uploads/presign", json=_valid_payload(file_size=-1))
    assert r.status_code == 422


# Boundary: exactly 100 MB is allowed
def test_presign_exactly_100mb_is_accepted(client):
    _as_creator(client)
    exactly_100mb = 100 * 1024 * 1024
    p_factory, p_bucket, p_public = _mock_r2()
    with p_factory, p_bucket, p_public:
        r = client.post("/api/uploads/presign", json=_valid_payload(file_size=exactly_100mb))
    assert r.status_code == 200


# ── POST /api/uploads/presign — success ───────────────────────────────────────


def test_presign_creator_success_response_shape(client):
    """Successful presign returns upload_url, public_url, key, required_headers."""
    _as_creator(client)
    p_factory, p_bucket, p_public = _mock_r2()
    with p_factory, p_bucket, p_public:
        r = client.post("/api/uploads/presign", json=_valid_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["upload_url"] == _PRESIGN_URL
    assert body["required_headers"] == {"Content-Type": "video/mp4"}
    assert "key" in body
    assert "public_url" in body


def test_presign_public_url_matches_pattern(client):
    """public_url must follow pattern: {public_base}/videos/{creator_id}/{uuid}.mp4"""
    _as_creator(client)
    p_factory, p_bucket, p_public = _mock_r2()
    with p_factory, p_bucket, p_public:
        r = client.post("/api/uploads/presign", json=_valid_payload())
    assert r.status_code == 200
    body = r.json()
    public_url = body["public_url"]
    assert public_url.startswith(f"{_PUBLIC_BASE}/videos/")
    assert public_url.endswith(".mp4")
    # key and public_url must be consistent
    assert body["public_url"] == f"{_PUBLIC_BASE}/{body['key']}"


def test_presign_key_matches_pattern(client):
    """Object key must follow pattern: videos/{creator_id}/{uuid}.mp4"""
    _as_creator(client)
    p_factory, p_bucket, p_public = _mock_r2()
    with p_factory, p_bucket, p_public:
        r = client.post("/api/uploads/presign", json=_valid_payload())
    assert r.status_code == 200
    key = r.json()["key"]
    parts = key.split("/")
    assert parts[0] == "videos"
    assert parts[1].isdigit()          # creator_id
    assert parts[2].endswith(".mp4")   # uuid.mp4


def test_presign_calls_generate_presigned_url_correctly(client):
    """Verifies the correct boto3 call is made (bucket, key, ContentType, ExpiresIn)."""
    _as_creator(client)
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = _PRESIGN_URL
    p_factory = patch("src.app.routers.creator.get_r2_client", return_value=mock_client)
    p_bucket = patch("src.app.routers.creator.get_bucket_name", return_value=_BUCKET)
    p_public = patch("src.app.routers.creator.get_public_base_url", return_value=_PUBLIC_BASE)
    with p_factory, p_bucket, p_public:
        r = client.post("/api/uploads/presign", json=_valid_payload())
    assert r.status_code == 200

    mock_client.generate_presigned_url.assert_called_once()
    call_kwargs = mock_client.generate_presigned_url.call_args
    assert call_kwargs[0][0] == "put_object"
    params = call_kwargs[1]["Params"]
    assert params["Bucket"] == _BUCKET
    assert params["ContentType"] == "video/mp4"
    assert params["Key"].startswith("videos/")
    assert params["Key"].endswith(".mp4")
    assert call_kwargs[1]["ExpiresIn"] == 3600


def test_presign_each_call_generates_unique_key(client):
    """Two presign requests must produce different keys (uuid uniqueness)."""
    _as_creator(client)
    p_factory, p_bucket, p_public = _mock_r2()
    with p_factory, p_bucket, p_public:
        r1 = client.post("/api/uploads/presign", json=_valid_payload())
        r2 = client.post("/api/uploads/presign", json=_valid_payload())
    assert r1.json()["key"] != r2.json()["key"]
    assert r1.json()["public_url"] != r2.json()["public_url"]


# ── POST /api/uploads/presign — R2 not configured ────────────────────────────


def test_presign_r2_not_configured_returns_503(client):
    """Missing R2 env vars → 503 Service Unavailable (not a 500 crash)."""
    _as_creator(client)
    # Patch get_r2_client to raise KeyError (simulates missing env var)
    with patch(
        "src.app.routers.creator.get_r2_client",
        side_effect=KeyError("R2_ACCOUNT_ID"),
    ):
        r = client.post("/api/uploads/presign", json=_valid_payload())
    assert r.status_code == 503
    assert "R2_ACCOUNT_ID" in r.json()["detail"]


# ── GET /creator/upload — SSR page ────────────────────────────────────────────


def test_upload_page_renders_for_creator(client):
    _as_creator(client)
    r = client.get("/creator/upload")
    assert r.status_code == 200
    assert b"upload-form" in r.content
    assert b"video/mp4" in r.content


def test_upload_page_blocked_for_learner(client):
    _as_learner(client)
    r = client.get("/creator/upload")
    assert r.status_code == 403


def test_upload_page_blocked_for_unauthenticated(client):
    r = client.get("/creator/upload")
    assert r.status_code == 401
