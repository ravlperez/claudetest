"""
Acceptance criteria for TASK 12:

POST /api/content/{id}/attempt (learner only)
  - 401 unauthenticated, 403 creator
  - 404 content not found, 409 draft
  - 422 empty answers, wrong count, unknown question_id, out-of-range / negative index
  - Scoring: correct_count / total_questions * 100
  - XP: 30 base + 10 if score>=80 + 20 if score==100; once per content per UTC day
  - Streak: created on first activity; +1 on consecutive day; reset on missed day;
            unchanged on same-day repeat (unit tests with monkeypatched date)
  - Returns: attempt_id, score_percent, correct_count, total_questions,
             xp_awarded, streak{current_streak_days, last_active_date_utc}

GET /content/{id}/quiz  (SSR learner quiz page)
  - 200 learner; 403 creator; 401 anon; 404 not found; 409 draft

GET /attempts/{id}  (SSR results page)
  - 200 for attempt owner; 403 different learner; 403 creator; 401 anon; 404 not found
  - Shows score, XP awarded, streak
"""

import src.app.routers.learner as learner_module

_CREATOR = {"email": "creator@example.com", "password": "pw123456", "role": "creator"}
_LEARNER = {"email": "learner@example.com", "password": "pw123456", "role": "learner"}
_LEARNER2 = {"email": "learner2@example.com", "password": "pw123456", "role": "learner"}

_CONTENT = {
    "language": "en",
    "level": "A1",
    "title": "Test Video",
    "video_url": "https://pub.example.com/v.mp4",
}


def _q(prompt="What?", correct=0):
    return {
        "prompt": prompt,
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_option_index": correct,
    }


def _setup_published_content(client, n_questions=3) -> int:
    """Create published content with n_questions MCQs (all correct_option_index=0)."""
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.post("/api/creator/content", json=_CONTENT)
    content_id = r.json()["id"]
    client.post(
        f"/api/creator/content/{content_id}/quiz",
        json={"questions": [_q(f"Q{i}") for i in range(n_questions)]},
    )
    client.post(f"/api/creator/content/{content_id}/publish")
    return content_id


def _login_learner(client) -> None:
    """Sign up and log in as learner with profile."""
    client.post("/api/auth/signup", json=_LEARNER)
    client.post("/api/learner/profile", json={"target_language": "en", "level": "A1"})


def _get_qids(client, content_id) -> list:
    r = client.get(f"/api/content/{content_id}/quiz")
    return [q["id"] for q in r.json()["quiz"]["questions"]]


def _correct_payload(qids) -> dict:
    """All answers with selected_index=0 (matches correct_option_index=0)."""
    return {"answers": [{"question_id": qid, "selected_index": 0} for qid in qids]}


def _wrong_payload(qids) -> dict:
    """All answers wrong (selected_index=1, correct=0)."""
    return {"answers": [{"question_id": qid, "selected_index": 1} for qid in qids]}


# ── POST /api/content/{id}/attempt — auth ─────────────────────────────────────


def test_submit_attempt_unauthenticated_returns_401(client):
    r = client.post("/api/content/1/attempt", json={"answers": []})
    assert r.status_code == 401


def test_submit_attempt_creator_returns_403(client):
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.post("/api/content/1/attempt", json={"answers": []})
    assert r.status_code == 403


# ── POST /api/content/{id}/attempt — not found / state ────────────────────────


def test_submit_attempt_content_not_found_returns_404(client):
    _login_learner(client)
    r = client.post(
        "/api/content/999/attempt",
        json={"answers": [{"question_id": 1, "selected_index": 0}]},
    )
    assert r.status_code == 404


def test_submit_attempt_draft_content_returns_409(client):
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.post("/api/creator/content", json=_CONTENT)
    content_id = r.json()["id"]
    _login_learner(client)
    r = client.post(
        f"/api/content/{content_id}/attempt",
        json={"answers": [{"question_id": 1, "selected_index": 0}]},
    )
    assert r.status_code == 409


# ── POST /api/content/{id}/attempt — validation ───────────────────────────────


def test_submit_attempt_empty_answers_returns_422(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    r = client.post(f"/api/content/{content_id}/attempt", json={"answers": []})
    assert r.status_code == 422


def test_submit_attempt_wrong_count_returns_422(client):
    content_id = _setup_published_content(client)  # 3 questions
    _login_learner(client)
    qids = _get_qids(client, content_id)
    # Submit only 1 answer instead of 3
    r = client.post(
        f"/api/content/{content_id}/attempt",
        json={"answers": [{"question_id": qids[0], "selected_index": 0}]},
    )
    assert r.status_code == 422


def test_submit_attempt_unknown_question_id_returns_422(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    payload = _correct_payload(qids)
    payload["answers"][0]["question_id"] = 99999
    r = client.post(f"/api/content/{content_id}/attempt", json=payload)
    assert r.status_code == 422


def test_submit_attempt_selected_index_out_of_range_returns_422(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    payload = _correct_payload(qids)
    payload["answers"][0]["selected_index"] = 100  # options only go 0-3
    r = client.post(f"/api/content/{content_id}/attempt", json=payload)
    assert r.status_code == 422


def test_submit_attempt_negative_selected_index_returns_422(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    payload = _correct_payload(qids)
    payload["answers"][0]["selected_index"] = -1
    r = client.post(f"/api/content/{content_id}/attempt", json=payload)
    assert r.status_code == 422


# ── POST /api/content/{id}/attempt — scoring ──────────────────────────────────


def test_submit_attempt_all_correct_returns_100_percent(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    r = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    assert r.status_code == 201
    body = r.json()
    assert body["score_percent"] == 100
    assert body["correct_count"] == 3
    assert body["total_questions"] == 3


def test_submit_attempt_all_wrong_returns_0_percent(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    r = client.post(f"/api/content/{content_id}/attempt", json=_wrong_payload(qids))
    assert r.status_code == 201
    body = r.json()
    assert body["score_percent"] == 0
    assert body["correct_count"] == 0
    assert body["total_questions"] == 3


def test_submit_attempt_returns_attempt_id(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    r = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    body = r.json()
    assert "attempt_id" in body
    assert isinstance(body["attempt_id"], int)


def test_submit_attempt_returns_streak_field(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    r = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    body = r.json()
    assert "streak" in body
    assert "current_streak_days" in body["streak"]
    assert "last_active_date_utc" in body["streak"]


# ── POST /api/content/{id}/attempt — XP rules (SPEC 6.2) ─────────────────────


def test_first_attempt_100_percent_awards_60_xp(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    r = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    assert r.json()["xp_awarded"] == 60  # 30 base + 10 (>=80) + 20 (==100)


def test_first_attempt_0_percent_awards_30_xp(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    r = client.post(f"/api/content/{content_id}/attempt", json=_wrong_payload(qids))
    assert r.json()["xp_awarded"] == 30  # base only


def test_first_attempt_exactly_80_percent_awards_40_xp(client):
    # 5 questions; 4/5 = 80% → +10 bonus
    content_id = _setup_published_content(client, n_questions=5)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    answers = [{"question_id": qid, "selected_index": 0} for qid in qids[:4]]
    answers.append({"question_id": qids[4], "selected_index": 1})  # wrong
    r = client.post(f"/api/content/{content_id}/attempt", json={"answers": answers})
    assert r.json()["xp_awarded"] == 40  # 30 base + 10 (>=80)


def test_second_attempt_same_day_awards_zero_xp(client, monkeypatch):
    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-15")
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)

    r1 = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    assert r1.json()["xp_awarded"] == 60  # 30 + 10 + 20

    r2 = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    assert r2.json()["xp_awarded"] == 0


def test_attempt_on_next_day_awards_xp_again(client, monkeypatch):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)

    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-15")
    r1 = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    assert r1.json()["xp_awarded"] == 60

    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-16")
    r2 = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    assert r2.json()["xp_awarded"] == 60


# ── POST /api/content/{id}/attempt — streak (SPEC 6.3) ────────────────────────


def test_streak_created_on_first_attempt(client, monkeypatch):
    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-15")
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)

    r = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    assert r.status_code == 201
    streak = r.json()["streak"]
    assert streak["current_streak_days"] == 1
    assert streak["last_active_date_utc"] == "2026-01-15"


def test_streak_unchanged_on_same_day_repeat(client, monkeypatch):
    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-15")
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)

    client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    r2 = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    assert r2.json()["streak"]["current_streak_days"] == 1


def test_streak_increments_on_consecutive_day(client, monkeypatch):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)

    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-15")
    client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))

    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-16")
    r2 = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    assert r2.json()["streak"]["current_streak_days"] == 2
    assert r2.json()["streak"]["last_active_date_utc"] == "2026-01-16"


def test_streak_resets_when_day_missed(client, monkeypatch):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)

    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-15")
    client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))

    # Skip Jan 16 entirely — streak must reset
    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-17")
    r2 = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    assert r2.json()["streak"]["current_streak_days"] == 1


def test_streak_grows_over_multiple_consecutive_days(client, monkeypatch):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)

    for day in ("2026-01-10", "2026-01-11", "2026-01-12"):
        monkeypatch.setattr(learner_module, "_current_utc_date", lambda d=day: d)
        r = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
        assert r.status_code == 201

    assert r.json()["streak"]["current_streak_days"] == 3


# ── GET /content/{id}/quiz — SSR quiz page ────────────────────────────────────


def test_quiz_page_renders_for_learner(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    r = client.get(f"/content/{content_id}/quiz")
    assert r.status_code == 200
    assert b"Quiz" in r.content


def test_quiz_page_shows_question_prompts(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    r = client.get(f"/content/{content_id}/quiz")
    assert r.status_code == 200
    text = r.text
    assert "Q0" in text
    assert "Q1" in text
    assert "Q2" in text


def test_quiz_page_blocked_for_creator(client):
    content_id = _setup_published_content(client)
    r = client.get(f"/content/{content_id}/quiz")
    assert r.status_code == 403


def test_quiz_page_blocked_for_unauthenticated(client):
    r = client.get("/content/1/quiz")
    assert r.status_code == 401


def test_quiz_page_not_found_returns_404(client):
    _login_learner(client)
    r = client.get("/content/999/quiz")
    assert r.status_code == 404


def test_quiz_page_draft_returns_409(client):
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.post("/api/creator/content", json=_CONTENT)
    content_id = r.json()["id"]
    _login_learner(client)
    r = client.get(f"/content/{content_id}/quiz")
    assert r.status_code == 409


# ── GET /attempts/{id} — SSR results page ────────────────────────────────────


def _submit_attempt(client, content_id, qids) -> int:
    r = client.post(f"/api/content/{content_id}/attempt", json=_correct_payload(qids))
    return r.json()["attempt_id"]


def test_results_page_renders_for_owner(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    attempt_id = _submit_attempt(client, content_id, qids)

    r = client.get(f"/attempts/{attempt_id}")
    assert r.status_code == 200
    assert b"Quiz Results" in r.content


def test_results_page_shows_score(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    attempt_id = _submit_attempt(client, content_id, qids)

    r = client.get(f"/attempts/{attempt_id}")
    assert b"100%" in r.content


def test_results_page_shows_xp(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    attempt_id = _submit_attempt(client, content_id, qids)

    r = client.get(f"/attempts/{attempt_id}")
    assert b"60 XP" in r.content  # 30 base + 10 (>=80) + 20 (==100)


def test_results_page_shows_zero_xp_for_repeat(client, monkeypatch):
    monkeypatch.setattr(learner_module, "_current_utc_date", lambda: "2026-01-15")
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    _submit_attempt(client, content_id, qids)  # first attempt earns XP
    attempt_id2 = _submit_attempt(client, content_id, qids)  # second gets 0

    r = client.get(f"/attempts/{attempt_id2}")
    assert b"already earned today" in r.content


def test_results_page_blocked_for_unauthenticated(client):
    r = client.get("/attempts/1")
    assert r.status_code == 401


def test_results_page_blocked_for_creator(client):
    client.post("/api/auth/signup", json=_CREATOR)
    r = client.get("/attempts/1")
    assert r.status_code == 403


def test_results_page_not_found_returns_404(client):
    _login_learner(client)
    r = client.get("/attempts/9999")
    assert r.status_code == 404


def test_results_page_blocked_for_different_learner(client):
    content_id = _setup_published_content(client)
    _login_learner(client)
    qids = _get_qids(client, content_id)
    attempt_id = _submit_attempt(client, content_id, qids)

    # Switch to learner2
    client.cookies.clear()
    client.post("/api/auth/signup", json=_LEARNER2)
    client.post("/api/learner/profile", json={"target_language": "en", "level": "A1"})

    r = client.get(f"/attempts/{attempt_id}")
    assert r.status_code == 403
