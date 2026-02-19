import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.app.database import engine

BASE_DIR = pathlib.Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify the DB is reachable at startup (also triggers the data/ mkdir in
    # database.py if it hasn't happened yet).
    with engine.connect():
        pass
    yield


app = FastAPI(title="Language App", lifespan=lifespan)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
