"""
Acceptance criteria for TASK 13:

GET /api/progress  (learner only)
  - 401 unauthenticated, 403 creator
  - 200: returns total_xp, current_streak_days, last_active_date_utc, recent_attempts
  - total_xp reflects accumulated XP from attempts
  - recent_attempts sorted newest first, max 10 entries
  - each attempt entry has: attempt_id, content_id, score_percent, xp_awarded, completed_at
  - returns zeros / empty list before any activity

GET /progress  (SSR, learner only)
  - 200 for learner; 403 creator; 401 unauthenticated
  - shows total_xp and streak values
  - shows "no attempts" state when empty
  - shows attempt rows after activity
"""

import src.app.routers.learner as learner_module

_CREATOR = {"email": "creator@example.com", "password": "pw123456", "role": "creator"}
_LEARNER = {"email": "learner@example.com", "password": "pw123456", "role": "learner"}

_CONTENT = {
    "language": "en",
    "level": "A1",
    "title": "Progress Test Video",
    "video_url": "https://pub.example.com/v.mp4",
}


def _q(prompt="What?", correct=0):
    return {
        "prompt": prompt,
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_option_index": correct,
    }


def _setup_published_content(client) -> int:
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.post("/api/creator/content", json=_CONTENT)
    content_id = r.json()["id"]
    client.post(
        f"/api/creator/content/{content_id}/quiz",
        json={"questions": [_q(f"Q{i}") for i in range(3)]},
    )
    client.post(f"/api/creator/content/{content_id}/publish")
    return content_id


def _login_learner(client) -> None:
    client.post("/api/auth/signup", json=_LEARNER)
    client.post("/api/learner/profile", json={"target_language": "en", "level": "A1"})


def _get_qids(client, content_id) -> list:
    r = client.get(f"/api/content/{content_id}/quiz")
    return [q["id"] for q in r.json()["quiz"]["questions"]]


def _correct_payload(qids) -> dict:
    return {"answers": [{"question_id": qid, "selected_index": 0} for qid in qids]}


def _submit_attempt(client, content_id, qids) -> dict:
    r = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    assert r.status_code == 201
    return r.json()


# ── GET /api/progress — auth ──────────────────────────────────────────────────


def test_progress_unauthenticated_returns_401(client):
    r = client.get("/api/progress")
    assert r.status_code == 401


def test_progress_creator_returns_403(client):
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.get("/api/progress")
    assert r.status_code == 403


# ── GET /api/progress — zero state ────────────────────────────────────────────


def test_progress_returns_zeros_before_any_attempt(client):
    _login_learner(client)
    r = client.get("/api/progress")
    assert r.status_code == 200
    body = r.json()
    assert body["total_xp"] == 0
    assert body["current_streak_days"] == 0
    assert body["last_active_date_utc"] is None
    assert body["recent_attempts"] == []


def test_progress_returns_zeros_even_without_profile(client):
    """Learner with no profile still gets 200 with zeros (not 412)."""
    client.post("/api/auth/signup", json=_LEARNER)
    r = client.get("/api/progress")
    assert r.status_code == 200
    body = r.json()
    assert body["total_xp"] == 0
    assert body["recent_attempts"] == []


# ── GET /api/progress — totals after attempt ──────────────────────────────────


def test_progress_reflects_xp_after_attempt(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    _submit_attempt(client, content_id, qids)  # all correct → 60 XP

    r = client.get("/api/progress")
    assert r.status_code == 200
    assert r.json()["total_xp"] == 60


def test_progress_reflects_streak_after_attempt(client, monkeypatch):
    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-15")
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    _submit_attempt(client, content_id, qids)

    r = client.get("/api/progress")
    body = r.json()
    assert body["current_streak_days"] == 1
    assert body["last_active_date_utc"] == "2026-01-15"


def test_progress_accumulates_xp_across_days(client, monkeypatch):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)

    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-15")
    _submit_attempt(client, content_id, qids)  # 60 XP

    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-16")
    _submit_attempt(client, content_id, qids)  # 60 XP again (new day)

    r = client.get("/api/progress")
    assert r.json()["total_xp"] == 120


# ── GET /api/progress — recent_attempts shape and ordering ────────────────────


def test_progress_recent_attempts_has_required_fields(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    _submit_attempt(client, content_id, qids)

    r = client.get("/api/progress")
    attempts = r.json()["recent_attempts"]
    assert len(attempts) == 1
    a = attempts[0]
    assert "attempt_id" in a
    assert "content_id" in a
    assert "score_percent" in a
    assert "xp_awarded" in a
    assert "completed_at" in a


def test_progress_recent_attempts_sorted_newest_first(client, monkeypatch):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)

    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-10")
    a1 = _submit_attempt(client, content_id, qids)

    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-11")
    a2 = _submit_attempt(client, content_id, qids)

    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-12")
    a3 = _submit_attempt(client, content_id, qids)

    r = client.get("/api/progress")
    ids = [a["attempt_id"] for a in r.json()["recent_attempts"]]
    # Newest (a3) first, oldest (a1) last
    assert ids == [a3["attempt_id"], a2["attempt_id"], a1["attempt_id"]]


def test_progress_recent_attempts_limited_to_10(client, monkeypatch):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)

    # Submit 11 attempts on 11 different days
    for day in range(1, 12):
        date_str = f"2026-01-{day:02d}"
        monkeypatch.setattr(learner_module, "_current_utc_date", lambda d=date_str: d)
        _submit_attempt(client, content_id, qids)

    r = client.get("/api/progress")
    assert len(r.json()["recent_attempts"]) == 10


def test_progress_recent_attempts_zero_xp_flagged(client, monkeypatch):
    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-15")
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)

    _submit_attempt(client, content_id, qids)  # earns XP
    _submit_attempt(client, content_id, qids)  # 0 XP (same day repeat)

    r = client.get("/api/progress")
    attempts = r.json()["recent_attempts"]
    xp_values = [a["xp_awarded"] for a in attempts]
    assert 0 in xp_values
    assert 60 in xp_values


def test_progress_attempt_content_id_matches(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    _submit_attempt(client, content_id, qids)

    r = client.get("/api/progress")
    a = r.json()["recent_attempts"][0]
    assert a["content_id"] == content_id


# ── GET /progress — SSR progress page ────────────────────────────────────────


def test_progress_page_renders_for_learner(client):
    _login_learner(client)
    r = client.get("/progress")
    assert r.status_code == 200
    assert b"My Progress" in r.content


def test_progress_page_blocked_for_creator(client):
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.get("/progress")
    assert r.status_code == 403


def test_progress_page_blocked_for_unauthenticated(client):
    r = client.get("/progress")
    assert r.status_code == 401


def test_progress_page_shows_total_xp(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    _submit_attempt(client, content_id, qids)

    r = client.get("/progress")
    assert r.status_code == 200
    assert b"60" in r.content  # total_xp


def test_progress_page_shows_empty_state_when_no_attempts(client):
    _login_learner(client)
    r = client.get("/progress")
    assert r.status_code == 200
    assert b"no-attempts" in r.content


def test_progress_page_shows_attempt_rows_after_activity(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    _submit_attempt(client, content_id, qids)

    r = client.get("/progress")
    assert r.status_code == 200
    assert b"Progress Test Video" in r.content
    assert b"100%" in r.content


def test_progress_page_shows_streak(client, monkeypatch):
    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-15")
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    _submit_attempt(client, content_id, qids)

    r = client.get("/progress")
    assert r.status_code == 200
    assert b"2026-01-15" in r.content
