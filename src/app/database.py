import os
import pathlib

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")

# Ensure the data directory exists when using the default SQLite path.
# This runs at import time so both `alembic upgrade head` and the app itself
# can create the file without an explicit `mkdir`.
if DATABASE_URL.startswith("sqlite:///"):
    _db_path = pathlib.Path(DATABASE_URL[len("sqlite:///"):])
    _db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    # Required for SQLite: allow the same connection across threads
    # (FastAPI may handle a request on a different thread than the one that
    # opened the connection).
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base class shared by all ORM models."""
