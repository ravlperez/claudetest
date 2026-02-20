"""
Acceptance criteria for TASK 8:
- Feed returns only content matching the learner's language and level
- Newest published content appears first
- Cursor-based load-more fetches the next page of items
- Drafts are excluded from the feed
- No profile → 412
- Creator → 403
- Unauthenticated → 401

VideoContent rows are inserted directly via the db_session fixture to avoid
depending on the creator upload endpoints (TASK 9+).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from src.app.auth import hash_password
from src.app.models import (
    CEFRLevel,
    ContentStatus,
    Language,
    LearnerProfile,
    Role,
    User,
    VideoContent,
)


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session(db_engine):
    """Bare SQLAlchemy session sharing the same in-memory DB as the client."""
    Session = sessionmaker(bind=db_engine)
    sess = Session()
    yield sess
    sess.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_creator(db) -> User:
    creator = User(
        email="creator@example.com",
        password_hash=hash_password("pass123"),
        role=Role.creator,
    )
    db.add(creator)
    db.flush()
    return creator


def _make_video(
    db,
    creator_id: int,
    language: str = "en",
    level: str = "B1",
    title: str = "Test Video",
    published: bool = True,
    published_at: datetime | None = None,
) -> VideoContent:
    vc = VideoContent(
        creator_id=creator_id,
        language=Language(language),
        level=CEFRLevel(level),
        title=title,
        video_url="https://example.com/test.mp4",
        status=ContentStatus.published if published else ContentStatus.draft,
        published_at=published_at if published else None,
    )
    if published and published_at is None:
        vc.published_at = _utcnow()
    db.add(vc)
    return vc


def _as_learner(client, language: str = "en", level: str = "B1"):
    client.post(
        "/api/auth/signup",
        json={"email": "learner@example.com", "password": "password123", "role": "learner"},
    )
    client.post("/api/learner/profile", json={"target_language": language, "level": level})


# ---------------------------------------------------------------------------
# GET /api/feed — auth / gating
# ---------------------------------------------------------------------------


def test_feed_api_unauthenticated_returns_401(client):
    r = client.get("/api/feed")
    assert r.status_code == 401


def test_feed_api_creator_returns_403(client):
    client.post(
        "/api/auth/signup",
        json={"email": "creator@example.com", "password": "password123", "role": "creator"},
    )
    r = client.get("/api/feed")
    assert r.status_code == 403


def test_feed_api_no_profile_returns_412(client):
    """Learner with no profile → 412 Precondition Failed."""
    client.post(
        "/api/auth/signup",
        json={"email": "learner@example.com", "password": "password123", "role": "learner"},
    )
    r = client.get("/api/feed")
    assert r.status_code == 412


# ---------------------------------------------------------------------------
# GET /api/feed — filtering
# ---------------------------------------------------------------------------


def test_feed_filters_by_language(client, db_session):
    creator = _make_creator(db_session)
    _make_video(db_session, creator.id, language="en", level="B1", title="English B1")
    _make_video(db_session, creator.id, language="fr", level="B1", title="French B1")
    db_session.commit()

    _as_learner(client, "en", "B1")
    r = client.get("/api/feed")
    assert r.status_code == 200
    titles = [v["title"] for v in r.json()["items"]]
    assert titles == ["English B1"]


def test_feed_filters_by_level(client, db_session):
    creator = _make_creator(db_session)
    _make_video(db_session, creator.id, language="en", level="B1", title="B1 Video")
    _make_video(db_session, creator.id, language="en", level="A2", title="A2 Video")
    db_session.commit()

    _as_learner(client, "en", "B1")
    r = client.get("/api/feed")
    assert r.status_code == 200
    titles = [v["title"] for v in r.json()["items"]]
    assert titles == ["B1 Video"]


def test_feed_excludes_drafts(client, db_session):
    creator = _make_creator(db_session)
    _make_video(db_session, creator.id, title="Published", published=True)
    _make_video(db_session, creator.id, title="Draft", published=False)
    db_session.commit()

    _as_learner(client)
    r = client.get("/api/feed")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Published"


def test_feed_empty_for_no_matching_content(client):
    _as_learner(client)
    r = client.get("/api/feed")
    assert r.status_code == 200
    assert r.json() == {"items": [], "next_cursor": None}


# ---------------------------------------------------------------------------
# GET /api/feed — ordering (newest first)
# ---------------------------------------------------------------------------


def test_feed_newest_published_first(client, db_session):
    creator = _make_creator(db_session)
    base = _utcnow()
    _make_video(db_session, creator.id, title="Older", published_at=base - timedelta(hours=2))
    _make_video(db_session, creator.id, title="Newer", published_at=base)
    _make_video(db_session, creator.id, title="Middle", published_at=base - timedelta(hours=1))
    db_session.commit()

    _as_learner(client)
    r = client.get("/api/feed")
    assert r.status_code == 200
    titles = [v["title"] for v in r.json()["items"]]
    assert titles == ["Newer", "Middle", "Older"]


# ---------------------------------------------------------------------------
# GET /api/feed — cursor pagination (load-more)
# ---------------------------------------------------------------------------


def test_feed_cursor_pagination_full_cycle(client, db_session):
    """Create 12 videos; first page returns 10 with a cursor; second returns 2 with no cursor."""
    creator = _make_creator(db_session)
    base = _utcnow()
    for i in range(12):
        _make_video(
            db_session,
            creator.id,
            title=f"Video {i:02d}",
            published_at=base - timedelta(minutes=i),
        )
    db_session.commit()

    _as_learner(client)

    # Page 1
    r1 = client.get("/api/feed?limit=10")
    assert r1.status_code == 200
    data1 = r1.json()
    assert len(data1["items"]) == 10
    assert data1["next_cursor"] is not None

    # Page 2
    r2 = client.get(f"/api/feed?limit=10&cursor={data1['next_cursor']}")
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["items"]) == 2
    assert data2["next_cursor"] is None

    # No duplicates across both pages
    all_titles = [v["title"] for v in data1["items"] + data2["items"]]
    assert len(set(all_titles)) == 12


def test_feed_cursor_no_next_when_exact_page_size(client, db_session):
    """Exactly 10 items with limit=10 → no next_cursor."""
    creator = _make_creator(db_session)
    base = _utcnow()
    for i in range(10):
        _make_video(db_session, creator.id, title=f"Video {i}", published_at=base - timedelta(minutes=i))
    db_session.commit()

    _as_learner(client)
    r = client.get("/api/feed?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 10
    assert data["next_cursor"] is None


def test_feed_invalid_cursor_returns_from_beginning(client, db_session):
    """An invalid/garbage cursor should be silently ignored (returns first page)."""
    creator = _make_creator(db_session)
    _make_video(db_session, creator.id, title="Only Video")
    db_session.commit()

    _as_learner(client)
    r = client.get("/api/feed?cursor=notavalidcursor")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Only Video"


# ---------------------------------------------------------------------------
# GET /api/feed — response shape
# ---------------------------------------------------------------------------


def test_feed_item_has_required_fields(client, db_session):
    creator = _make_creator(db_session)
    _make_video(db_session, creator.id, title="Shape Test", language="en", level="B1")
    db_session.commit()

    _as_learner(client)
    r = client.get("/api/feed")
    assert r.status_code == 200
    item = r.json()["items"][0]
    for field in ("id", "creator_id", "language", "level", "title", "caption",
                  "video_url", "thumbnail_url", "status", "published_at"):
        assert field in item, f"Missing field: {field}"
    assert item["status"] == "published"
    assert item["language"] == "en"
    assert item["level"] == "B1"


# ---------------------------------------------------------------------------
# GET /feed (SSR page) with content
# ---------------------------------------------------------------------------


def test_feed_page_shows_video_title(client, db_session):
    creator = _make_creator(db_session)
    _make_video(db_session, creator.id, title="My Learning Video")
    db_session.commit()

    _as_learner(client)
    r = client.get("/feed")
    assert r.status_code == 200
    assert b"My Learning Video" in r.content


def test_feed_page_shows_empty_state_when_no_content(client):
    _as_learner(client)
    r = client.get("/feed")
    assert r.status_code == 200
    assert b"No videos available" in r.content


def test_feed_page_has_load_more_button_when_more_pages(client, db_session):
    """If there are more items than the first page (>10), Load more button is present."""
    creator = _make_creator(db_session)
    base = _utcnow()
    for i in range(11):
        _make_video(db_session, creator.id, title=f"Video {i}", published_at=base - timedelta(minutes=i))
    db_session.commit()

    _as_learner(client)
    r = client.get("/feed")
    assert r.status_code == 200
    # The button element is rendered (not just referenced in JS)
    assert b'id="load-more-btn"' in r.content


def test_feed_page_no_load_more_when_single_page(client, db_session):
    """If content fits on one page, the Load more button element should not be rendered."""
    creator = _make_creator(db_session)
    _make_video(db_session, creator.id, title="Single Video")
    db_session.commit()

    _as_learner(client)
    r = client.get("/feed")
    assert r.status_code == 200
    # The button HTML element is absent (JS may still reference it by ID, that's fine)
    assert b'id="load-more-btn"' not in r.content
