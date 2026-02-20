# FINAL_CHECKLIST.md — Language App MVP Validation

Follow these steps to validate the full MVP in ≤ 10 minutes.
Run migrations and the seed script once before starting.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m src.app.scripts.seed
uvicorn src.app.main:app --reload
```

---

## 1. Health check (30 s)

```bash
curl http://127.0.0.1:8000/health
# Expected: {"status":"ok"}
```

- [ ] Returns `{"status":"ok"}` with HTTP 200

---

## 2. Signup + login (1 min)

- [ ] Open `http://127.0.0.1:8000/signup` — form renders without errors
- [ ] Sign up with a **new** email (e.g. `test@example.com`, password `Test1234!`)
- [ ] After signup, `/api/me` returns the new user's email and role
- [ ] Open `http://127.0.0.1:8000/login` — log in with wrong password → error message shown
- [ ] Log in with correct credentials → redirected to `/`
- [ ] `POST /logout` clears session → subsequent `/api/me` returns 401

---

## 3. Learner onboarding + feed (1.5 min)

Demo credentials: `demo.learner@langapp.dev` / `Demo1234!`

- [ ] Log in as demo learner
- [ ] Visit `http://127.0.0.1:8000/feed` — feed loads with at least one video card
- [ ] Card shows title, video player, language/level badge, and **Take quiz →** button
- [ ] Visit `http://127.0.0.1:8000/onboarding` — form pre-selects current language/level
- [ ] Change level to A2, save → redirected to `/feed` (feed is now empty, as expected)
- [ ] Change back to A1 via onboarding → feed shows video again

---

## 4. Learner quiz + XP + streak (2 min)

- [ ] Click **Take quiz →** on a video card → quiz page renders with video and questions
- [ ] Submit answers (all correct) → results page shows score 100%, XP awarded (60 XP)
- [ ] Submit the same quiz again → results page shows XP = 0 (already earned today)
- [ ] Visit `http://127.0.0.1:8000/progress` — shows total XP ≥ 60, streak ≥ 1

---

## 5. Creator workflow (2 min)

Demo credentials: `demo.creator@langapp.dev` / `Demo1234!`

- [ ] Log in as demo creator
- [ ] Visit `http://127.0.0.1:8000/creator` — seeded content appears with status "published"
- [ ] Click the content → detail page shows title, video URL, quiz state (3 questions)
- [ ] Visit `http://127.0.0.1:8000/creator/content/new` — form renders
- [ ] Create a new draft with any title, language, level, and a placeholder video URL
- [ ] Visit the quiz authoring page for the new draft
- [ ] Add 3 questions with 2–6 options each and save quiz
- [ ] Publish the content → status changes to "published"
- [ ] Log back in as learner → new content appears in feed (if language/level matches)

---

## 6. API consistency + error handling (1 min)

```bash
# 401 — not authenticated
curl -s http://127.0.0.1:8000/api/me | jq .
# Expected: {"detail":"Not authenticated"}

# 404 — content not found
curl -s http://127.0.0.1:8000/api/content/99999/quiz | jq .
# Expected: {"detail":"Content not found"}

# 422 — validation error
curl -s -X POST http://127.0.0.1:8000/api/auth/signup \
     -H "Content-Type: application/json" \
     -d '{"email":"bad","password":"x"}' | jq .
# Expected: 422 with validation details
```

- [ ] All API errors return JSON (no HTML stack traces)
- [ ] Status codes match the error type (401, 403, 404, 409, 422)

---

## 7. Logging (30 s)

Watch the uvicorn console while performing these actions:

- [ ] Failed login attempt → `auth_login_failure` line appears in logs
- [ ] Successful login → `auth_login_success` line appears in logs
- [ ] Publish a content item → `creator_publish` line appears in logs
- [ ] Submit a quiz attempt → `learner_attempt_submitted` with score/XP appears in logs

---

## 8. CI (automated — check GitHub Actions)

- [ ] All pytest tests pass locally: `python -m pytest`
- [ ] GitHub Actions CI workflow is green on the latest push

---

## Done

If all checkboxes above are ticked, the Language App MVP is ready for a live demo.
