# TASKS.md — Language App (Web) — MVP
Version: aligned with SPEC.md v1.0

Rules
- Each task should be doable in one sitting.
- Each task must be verifiable in 5–10 minutes with copy/paste steps.
- If a new decision appears during coding, pause and update SPEC.md + Decision Log before proceeding.

Dependencies
- Phase order is required (0 → 7). Within a phase, tasks are in recommended order.

---

## Phase 0 — Foundation (repo, structure, CI, deploy)

### TASK 0: Repository skeleton + FastAPI app bootstrap
Context
- Establish a clean base project structure and a running FastAPI app with SSR templates.

Objective
- App runs locally and serves a landing page plus health endpoint.

Scope
- Includes: project structure, FastAPI app, Jinja templates wiring, basic pages (/ and /health)
- Excludes: DB, auth, R2, business logic

Requirements
- FastAPI app entrypoint at src/app/main.py
- Jinja templates folder and at least one template used for landing page
- /health returns JSON {"status":"ok"}

Interfaces / Contracts
- GET /health -> 200 JSON
- GET / -> 200 HTML with links to /signup and /login

Acceptance Criteria
- [ ] /health returns {"status":"ok"}
- [ ] / renders HTML
- [ ] No stack traces in console on first run

Definition of Done
- App runs, minimal README includes run command

Risks & Notes
- Keep structure stable to avoid refactors later.

Manual Verification Plan
- python -m venv .venv
- pip install -r requirements.txt
- uvicorn src.app.main:app --reload
- curl http://127.0.0.1:8000/health
- open http://127.0.0.1:8000/

AI Output Requirements
- Files touched + why
- Commands to run
- Suggested next task

---

### TASK 1: Tooling baseline (format/lint), test harness, and CI workflow
Context
- You want a professional workflow with PRs and automatic checks.

Objective
- Tests run locally and in GitHub Actions on PR/push.

Scope
- Includes: pytest setup, a smoke test for /health, GitHub Actions workflow
- Excludes: business features

Requirements
- Add pytest
- Add at least one test: /health returns 200 and JSON status ok
- GitHub Actions: run tests on PR and push to main

Interfaces / Contracts
- `pytest` runs successfully

Acceptance Criteria
- [ ] `pytest` passes locally
- [ ] CI pipeline passes in GitHub Actions

Definition of Done
- CI yaml committed
- README updated with `pytest` command

Risks & Notes
- Keep CI minimal for speed.

Manual Verification Plan
- pytest
- Push branch + open PR + confirm checks pass

AI Output Requirements
- Files changed
- CI name + what it runs
- Next task suggestion

---

### TASK 2: Render deployment (prod-demo) + environment config scaffold
Context
- We need a public demo URL.

Objective
- App deployed to Render and /health works on the Render URL.

Scope
- Includes: Render start command docs, port config, prod env detection scaffold
- Excludes: DB persistence guarantees (SQLite demo only)

Requirements
- Add docs to README: how to deploy to Render
- Add settings scaffold (APP_ENV, SECRET_KEY) read from env
- Ensure uvicorn host/port works in Render (0.0.0.0 and Render port)

Interfaces / Contracts
- /health works in prod-demo URL

Acceptance Criteria
- [ ] Render service deploys successfully
- [ ] /health returns {"status":"ok"} in Render

Definition of Done
- README deployment section complete

Risks & Notes
- SQLite data may reset on redeploy; acceptable for demo.

Manual Verification Plan
- Create Render web service from GitHub repo
- Configure start command
- Visit https://<render-url>/health

AI Output Requirements
- Exact Render settings (build/start commands)
- Env vars list
- Next task suggestion

---

## Phase 1 — Database + Models + Migrations

### TASK 3: SQLAlchemy + Alembic setup with SQLite
Context
- We need a real DB layer with migrations to look professional.

Objective
- Alembic migrations run and create DB schema.

Scope
- Includes: SQLAlchemy engine/session, Alembic init/config, first migration skeleton
- Excludes: full tables (added in next task)

Requirements
- DB URL from env with sane default for local
- Alembic configured to autogenerate from models

Interfaces / Contracts
- `alembic revision --autogenerate`
- `alembic upgrade head`

Acceptance Criteria
- [ ] Migration can be generated and applied
- [ ] App starts with DB configured

Definition of Done
- Migration instructions in README

Risks & Notes
- Keep DB path consistent (e.g. ./data/app.db).

Manual Verification Plan
- alembic revision --autogenerate -m "init"
- alembic upgrade head
- Start app and hit /health

AI Output Requirements
- Files created/modified
- Commands to migrate
- Next task suggestion

---

### TASK 4: Implement core tables (User, profiles, content, quiz, attempts, xp, streak)
Context
- All MVP features depend on the schema.

Objective
- Data model from SPEC exists in SQLite via migrations.

Scope
- Includes: SQLAlchemy models + relationships + indexes + constraints, migration
- Excludes: endpoints/business logic

Requirements
- Tables per SPEC: User, LearnerProfile, CreatorProfile, VideoContent, Quiz, Question, QuizAttempt, XPEvent, Streak
- Constraints: unique email, quiz content unique, indexes for feed and daily XP enforcement

Interfaces / Contracts
- Alembic migration creates tables and indexes

Acceptance Criteria
- [ ] `alembic upgrade head` creates all tables
- [ ] Simple script can create a user row

Definition of Done
- Models documented briefly (docstring or README section)

Risks & Notes
- SQLite JSON stored as TEXT.

Manual Verification Plan
- alembic revision --autogenerate -m "core schema"
- alembic upgrade head
- (Optional) run a small python snippet to insert a user

AI Output Requirements
- Migration details
- Next task suggestion

---

## Phase 2 — Auth (signed cookie sessions + CSRF + rate limit)

### TASK 5: Authentication pages and API (signup/login/logout/me) with signed cookies
Context
- Both learner and creator flows require authentication.

Objective
- Users can sign up, log in, log out, and the app knows who is logged in.

Scope
- Includes: SSR pages (/signup, /login), API endpoints (/api/auth/*, /api/me), password hashing
- Excludes: onboarding and role-specific pages

Requirements
- Password hashing (bcrypt/argon2)
- Signed session cookie stores: user_id, role
- Session cookie flags: HttpOnly, SameSite=Lax, Secure in prod
- Basic login rate limiting (e.g. per-IP in memory for demo)

Interfaces / Contracts
- POST /api/auth/signup
- POST /api/auth/login
- GET /api/me
- POST /logout

Acceptance Criteria
- [ ] Signup creates a user
- [ ] Login sets cookie and /api/me returns user
- [ ] Logout clears cookie
- [ ] Wrong password returns 401
- [ ] Too many login attempts returns 429

Definition of Done
- Tests for signup/login/me pass in CI

Risks & Notes
- Rate limiting can be in-memory for demo.

Manual Verification Plan
- Run migrations
- Start app
- Sign up via UI
- Log in and hit /api/me
- Try wrong password and confirm 401
- Spam login to see 429

AI Output Requirements
- Files touched
- Test commands
- Next task suggestion

---

### TASK 6: CSRF protection for state-changing requests
Context
- Using cookies requires CSRF protection for POST forms.

Objective
- All browser POSTs include and validate CSRF tokens.

Scope
- Includes: CSRF token generation, template helper, middleware/dependency checks
- Excludes: API auth for non-browser clients (not needed)

Requirements
- CSRF token included in signup/login/logout and future forms
- Reject missing/invalid CSRF with 403

Interfaces / Contracts
- POST form endpoints validate CSRF

Acceptance Criteria
- [ ] Valid form submits work
- [ ] Removing CSRF token causes 403

Definition of Done
- At least one automated test covers CSRF failure

Risks & Notes
- Keep it simple: double-submit cookie or signed token.

Manual Verification Plan
- Submit signup normally (works)
- Submit without token (fails)

AI Output Requirements
- How CSRF works in this codebase
- Next task suggestion

---

## Phase 3 — Learner onboarding + feed read path

### TASK 7: Learner onboarding (profile create/read) + gating
Context
- Feed must be filtered by learner’s language and level.

Objective
- Learner can set target language and CEFR level; feed requires profile.

Scope
- Includes: onboarding page + API endpoints, validation of allowed languages and levels
- Excludes: video playback UI polish

Requirements
- Languages: en, es, fr only
- Levels: A1–C2
- Learner-only access; creators blocked (403)
- If profile missing, redirect to /onboarding

Interfaces / Contracts
- GET/POST /onboarding
- POST /api/learner/profile
- GET /api/learner/profile

Acceptance Criteria
- [ ] Learner can save profile
- [ ] Feed redirects to onboarding when missing profile
- [ ] Creator cannot access learner profile endpoints

Definition of Done
- Tests for profile create and gating

Risks & Notes
- Store language as short code for simplicity.

Manual Verification Plan
- Login as learner
- Visit /feed -> redirected to onboarding
- Save profile
- Visit /feed -> allowed

AI Output Requirements
- Files touched
- Next task suggestion

---

### TASK 8: Feed endpoint + SSR feed page with pagination
Context
- Core “reels-style” browsing experience.

Objective
- Learner sees a list of published videos filtered by language/level, newest first, with load-more pagination.

Scope
- Includes: GET /api/feed cursor pagination, GET /feed SSR page, minimal JS for load-more
- Excludes: quiz flow (next phase)

Requirements
- Only published content is shown
- Ordering: published_at desc
- Pagination: limit default 10, cursor-based or offset (cursor preferred)
- Feed page uses HTML5 <video> basic player

Interfaces / Contracts
- GET /api/feed?cursor=&limit=

Acceptance Criteria
- [ ] Feed returns only matching language/level
- [ ] Newest appears first
- [ ] Load more fetches next items

Definition of Done
- Test for feed filtering and ordering

Risks & Notes
- Cursor can be based on published_at + id.

Manual Verification Plan
- Seed data or create published content
- Open /feed, verify order and load more

AI Output Requirements
- Pagination strategy explained
- Next task suggestion

---

## Phase 4 — Creator upload + publish (R2 presign)

### TASK 9: R2 integration: presigned upload endpoint + creator upload UI
Context
- Real video upload is a core MVP requirement.

Objective
- Creator can request presigned URL, upload mp4 directly to R2, and receive a public URL to store.

Scope
- Includes: /api/uploads/presign, R2 client config, creator upload form, validations
- Excludes: quiz creation (next task)

Requirements
- Validate: mp4 only, content_type video/mp4, size <= 100MB
- Public URL pattern: videos/{creator_id}/{uuid}.mp4
- Bucket: no listing (config doc note)
- Secrets in env only (local .env, Render env vars)

Interfaces / Contracts
- POST /api/uploads/presign -> upload_url + public_url + required headers

Acceptance Criteria
- [ ] Creator can upload a real mp4 to R2 via browser
- [ ] The returned public_url is playable in browser
- [ ] Invalid type/too large rejected (422/413)

Definition of Done
- Integration tests for presign endpoint (mocked) + basic validation tests

Risks & Notes
- For demo, presign logic must be correct; keep errors clear.

Manual Verification Plan
- Login as creator
- Open /creator/upload
- Select mp4 < 100MB
- Upload completes
- Open public_url and confirm it plays

AI Output Requirements
- Env vars required
- Exact curl example for presign
- Next task suggestion

---

### TASK 10: Creator content creation + publish workflow (draft -> published)
Context
- Content must be created as draft, get quiz, then publish.

Objective
- Creator can create draft content with video_url and publish it after quiz exists.

Scope
- Includes: creator dashboard pages, create content draft, content status, publish endpoint
- Excludes: quiz authoring UI (next task)

Requirements
- VideoContent status defaults to draft
- Publish requires: video_url present AND quiz exists with 3–5 questions
- Creator can view their content list and statuses

Interfaces / Contracts
- GET /api/creator/content
- POST /api/creator/content
- POST /api/creator/content/{id}/publish

Acceptance Criteria
- [ ] Draft is created and appears in creator dashboard
- [ ] Publish fails if no quiz (409)
- [ ] Publish succeeds after quiz (once implemented) and sets published_at

Definition of Done
- Tests for draft creation and publish constraints

Risks & Notes
- Enforce creator ownership (creator_id must match session user).

Manual Verification Plan
- Create content draft
- Try publish -> should fail (no quiz)
- After next task, publish -> success

AI Output Requirements
- Files touched
- Next task suggestion

---

## Phase 5 — Quiz authoring + learner attempt + XP + streak + progress

### TASK 11: Creator quiz authoring (3–5 MCQ) and quiz retrieval
Context
- Learner quiz flow depends on quiz existence.

Objective
- Creator can add a quiz with 3–5 multiple choice questions; learners can fetch quiz for published content.

Scope
- Includes: POST /api/creator/content/{id}/quiz, SSR form to add questions, GET /api/content/{id}/quiz
- Excludes: attempt submission scoring (next task)

Requirements
- Exactly 3–5 questions required in MVP
- Each question: prompt, 2–6 options, correct_option_index valid
- Quiz is unique per content

Interfaces / Contracts
- POST /api/creator/content/{id}/quiz
- GET /api/content/{id}/quiz

Acceptance Criteria
- [ ] Creator can save a valid 3–5 question quiz
- [ ] Invalid question structure returns 422
- [ ] Learner cannot fetch quiz for draft content (409/404)

Definition of Done
- Tests for quiz validation

Risks & Notes
- Store options as JSON TEXT.

Manual Verification Plan
- Create draft content
- Add quiz 3–5 questions
- Publish content
- As learner, fetch quiz endpoint

AI Output Requirements
- Example request payloads
- Next task suggestion

---

### TASK 12: Learner attempt submission: scoring + XP awarding rules + streak updates
Context
- Core learning loop: take quiz -> score -> XP -> streak.

Objective
- Learner can submit answers, get score, XP awarded per rules (once per content per UTC day), and streak updates correctly.

Scope
- Includes: POST /api/content/{id}/attempt + SSR quiz submission, create QuizAttempt, XPEvent, update LearnerProfile.total_xp, update Streak
- Excludes: progress dashboard UI (next task)

Requirements
- Scoring per SPEC
- XP once per content per UTC day
- XP rules:
  - base 30
  - +10 if score>=80
  - +20 if score==100
- Streak UTC date logic
- Repeat attempts same day allowed, but xp_awarded=0

Interfaces / Contracts
- POST /api/content/{id}/attempt
- GET /attempts/{id} results page

Acceptance Criteria
- [ ] First attempt today awards XP correctly
- [ ] Second attempt same day awards 0 XP
- [ ] Streak increments when day changes (unit test with mocked date)
- [ ] Creator cannot submit attempts (403)

Definition of Done
- Unit tests for XP and streak logic
- Integration test for attempt endpoint

Risks & Notes
- Use a “current_utc_date” helper to make streak logic testable.

Manual Verification Plan
- As learner, take quiz once -> check xp_awarded>0
- Take again -> xp_awarded=0
- Check streak shows updated date

AI Output Requirements
- Explanation of how “once/day” is enforced
- Next task suggestion

---

### TASK 13: Progress dashboard (API + SSR page)
Context
- Learners must see XP, streak, and recent attempts.

Objective
- Progress page shows total_xp, streak, last_active_date_utc, recent attempts.

Scope
- Includes: GET /api/progress, GET /progress page
- Excludes: analytics for creators

Requirements
- recent_attempts sorted newest first, limit (e.g. 10)
- only learner access

Interfaces / Contracts
- GET /api/progress

Acceptance Criteria
- [ ] Progress shows correct totals after attempts
- [ ] Recent attempts list includes score and xp_awarded
- [ ] Creator blocked (403)

Definition of Done
- Test for progress endpoint

Risks & Notes
- Keep UI minimal but readable.

Manual Verification Plan
- Complete at least one attempt
- Visit /progress and confirm values

AI Output Requirements
- Files touched
- Next task suggestion

---

## Phase 6 — Seed data + demo polish

### TASK 14: Seed/demo data script and minimal UX polish
Context
- Demo needs content quickly without manual creation every time.

Objective
- One command seeds: 1 creator + 1 learner + at least 1 published content + quiz, compatible with local dev.

Scope
- Includes: seed script/command, small UI polish (nav links, empty states)
- Excludes: new features

Requirements
- Seed uses supported languages (en/es/fr) and CEFR
- Optionally uses a placeholder video_url if no real upload available (clearly documented)

Interfaces / Contracts
- `python -m src.app.scripts.seed` (or similar)

Acceptance Criteria
- [ ] Seed command runs idempotently (or clearly warns)
- [ ] After seeding, learner feed is not empty
- [ ] Demo can be shown in < 2 minutes after setup

Definition of Done
- README includes seed usage

Risks & Notes
- If using placeholder URL, note it’s for demo only.

Manual Verification Plan
- Run migrations
- Run seed
- Login as learner, open feed, take quiz

AI Output Requirements
- Seed credentials (demo emails/passwords)
- Next task suggestion

---

## Phase 7 — Hardening-lite (within demo constraints)

### TASK 15: Logging, error handling, and final verification checklist
Context
- We want a “professional” finish without production complexity.

Objective
- Key events logged; errors return consistent JSON; final checklist for demo.

Scope
- Includes: structured logs for key events, consistent error responses for APIs, final manual checklist doc
- Excludes: admin tools, advanced monitoring

Requirements
- Log events: login success/failure, publish, attempt submitted (score, xp_awarded)
- Basic error handler for API routes (JSON errors with message/code)
- Add FINAL_CHECKLIST.md

Interfaces / Contracts
- API error responses consistent (e.g. {"error": {"code": "...", "message": "..."}})

Acceptance Criteria
- [ ] Logs appear locally and in Render
- [ ] API errors are consistent and not stack traces
- [ ] FINAL_CHECKLIST.md can be followed in 10 minutes to validate MVP

Definition of Done
- CI passing
- Docs updated

Risks & Notes
- Keep logging lightweight.

Manual Verification Plan
- Run through FINAL_CHECKLIST.md steps

AI Output Requirements
- List of events logged
- Next logical post-MVP task suggestions (optional)

---

# End
