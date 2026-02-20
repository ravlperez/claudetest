import logging
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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


logger = logging.getLogger(__name__)

app = FastAPI(title="Language App", lifespan=lifespan)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler: return clean JSON instead of leaking stack traces."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "An internal server error occurred"}},
    )


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
