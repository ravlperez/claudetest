# SPEC.md — Language App (Web) — MVP

## 0. Constraints

- Purpose: demo-quality MVP to showcase a professional dev workflow (GitHub branches + PRs + CI), not a revenue product.
- Budget: $0 target (free tiers only). Avoid paid services.
- Team: solo.
- Quality: usable MVP demo (clean code, migrations, tests, CI), not production-hardening.
- Platforms: web only. No mobile app. No multi-language UI.
- Users target: small demo usage (single digits to low tens).
- Deployment: dev local + prod-demo on Render (Render URL is enough).
- Storage: Cloudflare R2 public objects. No paid CDN, no transcoding.

## 1. Overview

Language App is a web-based learning platform with a vertical short-video feed (Reels-style) where creators upload language-learning videos. Each video includes a short quiz. Learners earn XP, maintain streaks, and track progress.

The MVP focuses on delivering a complete end-to-end experience:
- Real video uploads to object storage (R2) via presigned URL
- Quiz-taking flow
- XP and daily streak tracking
- Creator publish workflow
- Simple SSR web UI (FastAPI + Jinja) with a small amount of JS for a reels-like feed

## 2. Decisions (locked)

- Frontend: server-rendered pages using FastAPI + Jinja templates; small JS for feed interactions.
- Backend: FastAPI.
- Database: SQLite.
- ORM: SQLAlchemy 2.0.
- Migrations: Alembic.
- Auth: cookies with signed session cookie (store minimal data: user_id, role). CSRF enabled for forms.
- Email verification: no (MVP).
- Password reset: no (MVP).
- Login protection: basic rate limiting on auth endpoints.
- Video storage: Cloudflare R2 (S3-compatible).
- Upload strategy: direct browser upload to R2 using presigned URL from backend.
- Playback: public objects (simple URL).
- Transcoding: no. Accept mp4 with h264/aac and validate size/duration constraints.
- Languages supported in MVP: English, Spanish, French.
- CEFR levels: A1, A2, B1, B2, C1, C2.
- Content states: draft -> published.
- Feed ordering: newest published first. No recommendations.
- Streak timezone: UTC (calendar date by UTC).
- Deploy: Render for prod-demo. Local dev for development.
- CI: GitHub Actions runs lint (optional) + tests on PR and main pushes.
- Branching: protected main; PRs required from feature branches.
- Demo/seed data: yes, provide a script/command to seed minimal content.

## 3. Users and roles

### 3.1 Roles

- learner
- creator

Roles are mutually exclusive in MVP.

### 3.2 Learner capabilities

- Sign up / log in
- Complete onboarding (choose target language + CEFR level)
- Scroll feed filtered by their language + level
- Watch a video and take its quiz
- Receive score, XP updates (with daily limits), and streak updates
- View progress dashboard (total XP, streak, completed attempts)

### 3.3 Creator capabilities

- Sign up / log in as creator
- Upload short video file
- Create quiz (3–5 multiple-choice questions)
- Publish content (draft -> published)
- View their content list and status (draft/published)

## 4. MVP scope

### 4.1 Included

- SSR web app (FastAPI + Jinja)
- Authentication (email + password)
- Onboarding: language + CEFR selection
- Vertical feed filtered by language + level
- Video upload to R2 using presigned URL
- Quiz system: multiple choice only
- XP system + rules
- Daily streak system (UTC)
- Progress page for learners
- Creator dashboard + upload + quiz creation + publish

### 4.2 Excluded

- Payments, subscriptions, marketplace
- Private lessons or scheduling
- Creator monetization
- ML-based recommendations
- Comments, likes, social features, messaging
- Advanced moderation/admin panel
- Push notifications
- Mobile app
- Multi-language UI
- Analytics dashboards beyond basic learner progress

## 5. Core user journeys (end-to-end)

### 5.1 Learner journey

1) Sign up / log in
2) Onboarding: choose target language + CEFR level
3) Open feed (filtered)
4) Open a video, watch, start quiz
5) Submit quiz attempt
6) See results page (score, XP gained)
7) Progress page shows updated XP, streak, recent attempts

### 5.2 Creator journey

1) Sign up / log in as creator
2) Creator dashboard shows list (initially empty)
3) Create new content draft:
   - request presigned upload URL
   - upload video directly to R2
   - create content record with video_url
4) Add quiz (3–5 questions)
5) Publish
6) Content appears in learner feed (matching language + level)

## 6. Business rules

### 6.1 Quiz scoring

- correct_count = number of correct answers
- total_questions = number of questions
- score_percent = (correct_count / total_questions) * 100

### 6.2 XP rules

- Completing a quiz grants XP at most once per user per content per UTC day.
- Base XP: 30
- Bonus:
  - +10 XP if score_percent >= 80
  - +20 XP if score_percent == 100
- Repeating the same quiz on the same UTC day grants 0 XP.

### 6.3 Streak rules (UTC)

- Streak increases by 1 if the learner completes at least one quiz on a new UTC day.
- If a UTC day is missed (no quiz completed), the streak resets to 0 on next activity.
- last_active_date is stored as a UTC date (YYYY-MM-DD).

### 6.4 Feed rules

- Feed is filtered by:
  - learner_profile.target_language
  - learner_profile.level
- Ordering: newest published content first.
- No recommendation logic.

### 6.5 Video constraints

- Maximum duration: 60 seconds (validated by metadata where possible; at minimum enforce size and extension)
- Maximum size: 100 MB
- Allowed formats: mp4 (h264 video, aac audio)
- No transcoding

## 7. Data model (entities and relationships)

Notes:
- All timestamps are stored in UTC.
- Use integer primary keys (autoincrement) for SQLite.
- Use foreign keys and indexes explicitly.

### 7.1 Tables

User
- id (PK)
- email (unique, indexed)
- password_hash
- role (learner | creator) (indexed)
- created_at

LearnerProfile
- user_id (PK, FK -> User.id)
- target_language (enum-like string: en|es|fr) (indexed)
- level (A1|A2|B1|B2|C1|C2) (indexed)
- total_xp (int, default 0)
- created_at

CreatorProfile
- user_id (PK, FK -> User.id)
- display_name
- bio (nullable)
- created_at

VideoContent
- id (PK)
- creator_id (FK -> User.id) (indexed)
- language (en|es|fr) (indexed)
- level (A1|A2|B1|B2|C1|C2) (indexed)
- title
- caption (nullable)
- status (draft|published) (indexed)
- video_url (public R2 URL)
- thumbnail_url (nullable)
- published_at (nullable, indexed)
- created_at

Quiz
- id (PK)
- content_id (unique, FK -> VideoContent.id)
- created_at

Question
- id (PK)
- quiz_id (FK -> Quiz.id) (indexed)
- type (fixed: multiple_choice)
- prompt
- options_json (JSON string)
- correct_option_index (int)
- created_at

QuizAttempt
- id (PK)
- user_id (FK -> User.id) (indexed)
- content_id (FK -> VideoContent.id) (indexed)
- quiz_id (FK -> Quiz.id)
- score_percent (int)
- correct_count (int)
- total_questions (int)
- xp_awarded (int)
- completed_at (timestamp, indexed)
- completed_date_utc (date string YYYY-MM-DD, indexed)

XPEvent
- id (PK)
- user_id (FK -> User.id) (indexed)
- content_id (FK -> VideoContent.id, nullable)
- reason (quiz_completed | streak_bonus)
- xp_amount (int)
- created_at
- created_date_utc (date string YYYY-MM-DD, indexed)

Streak
- user_id (PK, FK -> User.id)
- current_streak_days (int, default 0)
- last_active_date_utc (date string YYYY-MM-DD, nullable)

### 7.2 Indexes and constraints

- User.email unique
- VideoContent: index (language, level, status, published_at desc) for feed
- Quiz: content_id unique (one quiz per content in MVP)
- QuizAttempt: index (user_id, content_id, completed_date_utc) to enforce XP once/day
- XPEvent: index (user_id, created_date_utc)

## 8. Web pages (SSR routes)

Public
- GET / : landing page with links to /signup and /login

Auth
- GET /signup : signup form
- POST /signup : create user
- GET /login : login form
- POST /login : authenticate and set session cookie
- POST /logout : clear session

Learner
- GET /onboarding : onboarding form
- POST /onboarding : save learner profile
- GET /feed : vertical feed
- GET /content/{id}/quiz : quiz page
- POST /content/{id}/attempt : submit attempt
- GET /attempts/{id} : results page
- GET /progress : progress dashboard

Creator
- GET /creator : creator dashboard
- GET /creator/upload : upload form
- POST /creator/content : create content draft (metadata + video_url)
- GET /creator/content/{id} : content detail page (status, quiz)
- POST /creator/content/{id}/quiz : create/update quiz
- POST /creator/content/{id}/publish : publish

## 9. API endpoints (JSON)

All API endpoints are under /api and require:
- authenticated session cookie except signup/login/presign (presign requires creator auth)
- CSRF protection for state-changing requests from browser (implementation detail)

### 9.1 Auth

POST /api/auth/signup
Request
{
  "email": "user@example.com",
  "password": "password123",
  "role": "learner"
}
Responses
- 201 created
{
  "id": 1,
  "email": "user@example.com",
  "role": "learner"
}
Errors
- 409 email exists
- 422 validation

POST /api/auth/login
Request
{
  "email": "user@example.com",
  "password": "password123"
}
Responses
- 200 ok
{
  "id": 1,
  "email": "user@example.com",
  "role": "learner"
}
Side effect: sets signed session cookie
Errors
- 401 invalid credentials
- 429 rate limited

GET /api/me
Response
- 200 ok
{
  "id": 1,
  "email": "user@example.com",
  "role": "learner"
}
Errors
- 401 not authenticated

### 9.2 Learner profile

POST /api/learner/profile
Request
{
  "target_language": "en",
  "level": "A2"
}
Response
- 200 ok
{
  "user_id": 1,
  "target_language": "en",
  "level": "A2",
  "total_xp": 0
}
Errors
- 401 not authenticated
- 403 wrong role
- 422 invalid language/level

GET /api/learner/profile
Response
- 200 ok (same shape as above)
Errors
- 401 not authenticated
- 404 not set

### 9.3 Feed

GET /api/feed?cursor=...&limit=10
Behavior
- requires learner role and learner profile exists
- filters by learner target_language and level
- returns newest published first using cursor pagination

Response
- 200 ok
{
  "items": [
    {
      "id": 10,
      "creator_id": 5,
      "language": "en",
      "level": "A2",
      "title": "Past simple in 30s",
      "caption": "Quick example",
      "video_url": "https://public-r2-url/videos/5/uuid.mp4",
      "status": "published",
      "published_at": "2026-02-19T00:00:00Z"
    }
  ],
  "next_cursor": "opaque_cursor_or_null"
}
Errors
- 401 not authenticated
- 403 wrong role
- 412 profile required (if onboarding not completed)

### 9.4 Quiz

GET /api/content/{id}/quiz
Response
- 200 ok
{
  "content": {
    "id": 10,
    "title": "Past simple in 30s",
    "video_url": "..."
  },
  "quiz": {
    "id": 7,
    "questions": [
      {
        "id": 1,
        "type": "multiple_choice",
        "prompt": "Choose the correct form",
        "options": ["go", "went", "gone", "going"]
      }
    ]
  }
}
Errors
- 401 not authenticated
- 403 wrong role
- 404 not found
- 409 not published (if learner tries to access draft)

POST /api/content/{id}/attempt
Request
{
  "answers": [
    { "question_id": 1, "selected_index": 1 }
  ]
}
Response
- 201 created
{
  "attempt_id": 55,
  "score_percent": 100,
  "correct_count": 1,
  "total_questions": 1,
  "xp_awarded": 50,
  "streak": {
    "current_streak_days": 3,
    "last_active_date_utc": "2026-02-19"
  }
}
Errors
- 401 not authenticated
- 403 wrong role
- 404 not found
- 422 invalid answers
- 409 already attempted today for XP (still allow attempt, but xp_awarded=0)

Rule for repeat same day
- Attempts are allowed, but xp_awarded becomes 0 if already earned XP for that content on that UTC day.

### 9.5 Progress

GET /api/progress
Response
- 200 ok
{
  "total_xp": 120,
  "current_streak_days": 3,
  "last_active_date_utc": "2026-02-19",
  "recent_attempts": [
    {
      "attempt_id": 55,
      "content_id": 10,
      "score_percent": 100,
      "xp_awarded": 50,
      "completed_at": "2026-02-19T01:02:03Z"
    }
  ]
}
Errors
- 401 not authenticated
- 403 wrong role

### 9.6 Creator content

GET /api/creator/content
Response
- 200 ok
{
  "items": [
    {
      "id": 10,
      "title": "Past simple in 30s",
      "status": "draft",
      "created_at": "..."
    }
  ]
}
Errors
- 401 not authenticated
- 403 wrong role

POST /api/creator/content
Request
{
  "language": "en",
  "level": "A2",
  "title": "Past simple in 30s",
  "caption": "Quick example",
  "video_url": "https://public-r2-url/videos/creator/uuid.mp4"
}
Response
- 201 created
{
  "id": 10,
  "status": "draft"
}
Errors
- 401 not authenticated
- 403 wrong role
- 422 invalid language/level
- 413 too large (if enforced earlier)

POST /api/creator/content/{id}/quiz
Request
{
  "questions": [
    {
      "prompt": "Choose the correct form",
      "options": ["go", "went", "gone", "going"],
      "correct_option_index": 1
    }
  ]
}
Response
- 200 ok
{
  "quiz_id": 7,
  "question_count": 1
}
Rules
- Must be 3–5 questions in MVP.
Errors
- 401 not authenticated
- 403 wrong role
- 404 not found
- 422 invalid question structure or not 3–5

POST /api/creator/content/{id}/publish
Response
- 200 ok
{
  "id": 10,
  "status": "published",
  "published_at": "..."
}
Rules
- content must have video_url and a valid quiz (3–5 questions).
Errors
- 401 not authenticated
- 403 wrong role
- 404 not found
- 409 cannot publish without quiz or video

### 9.7 Uploads (presign)

POST /api/uploads/presign
Request
{
  "filename": "myvideo.mp4",
  "content_type": "video/mp4",
  "size_bytes": 104857600
}
Response
- 200 ok
{
  "upload_url": "https://...presigned...",
  "public_url": "https://public-r2-url/videos/{creator_id}/{uuid}.mp4",
  "method": "PUT",
  "headers": {
    "Content-Type": "video/mp4"
  }
}
Rules
- creator role only
- enforce size <= 100MB
- enforce extension mp4 and content_type video/mp4
Errors
- 401 not authenticated
- 403 wrong role
- 413 too large
- 422 invalid type

## 10. Security and privacy (MVP)

- Passwords stored as strong hashes (bcrypt or argon2).
- Session cookie:
  - HttpOnly, Secure (in Render), SameSite=Lax
  - Signed to prevent tampering
- CSRF protection for all POST endpoints from browser.
- Basic rate limiting on login (and optionally signup).
- R2 bucket: public reads, no listing. Objects stored under videos/{creator_id}/{uuid}.mp4.
- Do not store secrets in GitHub. Use .env locally and Render environment variables.

## 11. Non-functional requirements (MVP)

Performance
- Feed loads first page within reasonable time for demo usage.
- Pagination supports limit default 10.

Reliability
- Demo tolerates restarts; data persistence on Render is not guaranteed with SQLite.

Cost
- Must remain within free tiers.

Observability
- Structured logs for key events:
  - auth_login_success/auth_login_failure
  - creator_publish
  - learner_attempt_submitted (score, xp_awarded)
- Minimal error logging with request id.

## 12. Deployment

Local (dev)
- Run with uvicorn
- SQLite file stored locally (e.g. ./data/app.db)

Render (prod-demo)
- FastAPI service deployed from GitHub
- Environment variables set in Render:
  - APP_ENV=prod
  - SECRET_KEY=...
  - R2_ENDPOINT=...
  - R2_ACCESS_KEY_ID=...
  - R2_SECRET_ACCESS_KEY=...
  - R2_BUCKET=...
  - R2_PUBLIC_BASE_URL=...
- SQLite in Render: best-effort for demo; data may be lost on redeploy/restart.

## 13. Testing and verification

Automated tests (minimum)
- Auth: signup/login/me
- Creator: create content draft, add quiz, publish
- Learner: onboarding, feed returns published content, attempt awards xp once/day
- Streak: increments on new UTC day, resets if missed (unit tests with fixed dates)

Manual verification (5–10 minutes per flow)

Creator flow
1) Sign up as creator
2) Request presign, upload mp4 to R2
3) Create content draft with returned public_url
4) Add 3–5 quiz questions
5) Publish
6) Verify it appears in feed for matching language/level

Learner flow
1) Sign up as learner
2) Onboarding: choose language and level
3) Open feed, select a published content
4) Open quiz and submit
5) Verify score, xp_awarded, streak update
6) Open progress page and verify totals

## 14. Changelog

- v1.0: decisions locked for demo MVP (SQLite + signed cookie auth + R2 public storage + Render prod-demo).

## 15. Decision log (summary)

- DB: SQLite (demo)
- Auth: signed cookie session + CSRF + basic rate limiting
- Storage: Cloudflare R2 public, presigned uploads, no listing
- Deploy: Render prod-demo + local dev
- No email verification, no password reset, no transcoding
- Languages: English, Spanish, French
- Feed: newest published first, pagination
- Streak: UTC
- Repo workflow: feature branches + PRs + GitHub Actions CI
