# Language App

A web-based language-learning platform with short videos and quizzes.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.app.main:app --reload
```

Then open:
- http://127.0.0.1:8000/ — landing page
- http://127.0.0.1:8000/health — health check

## Testing

```bash
pytest
```

## Deploying to Render

1. Push code to GitHub.
2. In the Render dashboard: **New → Web Service → Connect your repo**.
3. Configure the service:
   - **Environment**: Python 3
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn src.app.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables in Render → **Environment**:

   | Variable | Value |
   |----------|-------|
   | `APP_ENV` | `production` |
   | `SECRET_KEY` | *(generate: `python -c "import secrets; print(secrets.token_hex(32))"`)* |

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
    config.py        # APP_ENV + SECRET_KEY read from environment
    main.py          # FastAPI app entrypoint
    templates/       # Jinja2 SSR templates
      base.html
      index.html
.env.example         # Copy to .env for local dev (gitignored)
requirements.txt
```
