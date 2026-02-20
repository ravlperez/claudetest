import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.app.database import engine
from src.app.routers import auth as auth_router
from src.app.routers import creator as creator_router
from src.app.routers import learner as learner_router

BASE_DIR = pathlib.Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify the DB is reachable at startup (also triggers the data/ mkdir in
    # database.py if it hasn't happened yet).
    with engine.connect():
        pass
    yield


app = FastAPI(title="Language App", lifespan=lifespan)

app.include_router(auth_router.router)
app.include_router(creator_router.router)
app.include_router(learner_router.router)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(request, "index.html")
