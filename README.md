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

## Project structure

```
src/
  app/
    main.py          # FastAPI app entrypoint
    templates/       # Jinja2 SSR templates
      base.html
      index.html
requirements.txt
```
