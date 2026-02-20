# Language App

A web-based language-learning platform with short videos and quizzes.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # create/migrate the database
python -m src.app.scripts.seed  # (optional) load demo data
alembic upgrade head
uvicorn src.app.main:app --reload
```

Then open:
- http://127.0.0.1:8000/ — landing page
- http://127.0.0.1:8000/health — health check

## Demo: quick 2-minute walkthrough

After running migrations and the seed script the app is ready to demo immediately.

**Demo credentials** (created by the seed script):

| Role    | Email                       | Password   |
|---------|-----------------------------|------------|
| Creator | demo.creator@langapp.dev    | Demo1234!  |
| Learner | demo.learner@langapp.dev    | Demo1234!  |

**Creator flow:**
1. Log in as creator → `/creator` shows the seeded content
2. `/creator/upload` — upload a real mp4 to R2 (R2 env vars required)
3. `/creator/content/{id}/quiz` — edit the seeded quiz

**Learner flow:**
1. Log in as learner → auto-redirected to `/feed` (profile already set: English A1)
2. Click **Take quiz →** on the seeded video card
3. Submit answers → view score, XP, and streak on the results page
4. `/progress` — see accumulated XP and attempt history

> **Note:** The seeded content uses a public-domain placeholder MP4. Replace
> `video_url` in the database (or upload via the creator UI) with a real R2 URL
> for a fully working demo.

### Seed is idempotent

Running the seed command twice is safe — it detects existing demo accounts and
skips without inserting duplicates:

```
[seed] Demo data already present ('demo.creator@langapp.dev' exists). Skipping.
```

## Testing

```bash
python -m pytest
```

## Database migrations

The app uses Alembic to manage the SQLite schema. Run these commands from the repo root:

```bash
# Apply all pending migrations (creates data/app.db on first run):
alembic upgrade head

# After adding or changing ORM models, generate a new migration:
alembic revision --autogenerate -m "describe your change"

# Roll back one step:
alembic downgrade -1
```

> `data/app.db` is gitignored. The `data/` directory is created automatically
> on first run (by `database.py` or `alembic upgrade head`).

## Deploying to Render

1. Push code to GitHub.
2. In the Render dashboard: **New → Web Service → Connect your repo**.
3. Configure the service:
   - **Environment**: Python 3
   - **Build command**: `pip install -r requirements.txt && alembic upgrade head`
   - **Start command**: `uvicorn src.app.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables in Render → **Environment**:

   | Variable               | Value                                                      |
   |------------------------|------------------------------------------------------------|
   | `APP_ENV`              | `production`                                               |
   | `SECRET_KEY`           | *(generate: `python -c "import secrets; print(secrets.token_hex(32))"`)* |
   | `R2_ACCOUNT_ID`        | *(Cloudflare R2 account ID)*                              |
   | `R2_ACCESS_KEY_ID`     | *(R2 API token access key)*                               |
   | `R2_SECRET_ACCESS_KEY` | *(R2 API token secret)*                                   |
   | `R2_BUCKET_NAME`       | *(R2 bucket name)*                                        |
   | `R2_PUBLIC_DOMAIN`     | *(public R2 bucket domain, e.g. `https://pub.example.com`)* |

5. Click **Deploy**. Once live, verify:
   ```
   curl https://<your-render-url>/health
   # Expected: {"status":"ok"}
   ```

> **Note**: SQLite data resets on each Render redeploy (no persistent disk on free tier). This is acceptable for demo purposes.

## Project structure

```
src/
  app/
    config.py        # APP_ENV + SECRET_KEY settings (read from environment)
    database.py      # SQLAlchemy engine, SessionLocal, DeclarativeBase
    main.py          # FastAPI app entrypoint
    models.py        # ORM models (User, VideoContent, Quiz, QuizAttempt, …)
    auth.py          # Password hashing, signed session cookies, rate limiting
    csrf.py          # CSRF token generation and validation
    r2.py            # Cloudflare R2 client factory (presigned URLs)
    routers/
      creator.py     # Creator API + SSR pages (upload, content, quiz, publish)
      learner.py     # Learner API + SSR pages (feed, quiz, attempt, progress)
    scripts/
      seed.py        # Demo data seed script
    templates/       # Jinja2 SSR templates
alembic/             # Alembic migration environment
  env.py
  versions/
alembic.ini
requirements.txt
tests/
  conftest.py        # Shared pytest fixtures (in-memory SQLite TestClient)
  test_auth.py
  test_csrf.py
  test_feed.py
  test_learner.py
  test_models.py
  test_content.py
  test_quiz.py
  test_uploads.py
  test_attempts.py
  test_progress.py
  test_seed.py
```
