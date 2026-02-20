"""
Shared pytest fixtures for Language App tests.

Provides:
- db_engine  – in-memory SQLite engine with all tables created
- client     – FastAPI TestClient with get_db overridden to use in-memory DB
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.app.models  # registers all models with Base.metadata  # noqa: F401
from src.app.auth import _reset_rate_limits
from src.app.database import Base, get_db
from src.app.main import app


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the in-memory login-attempt counter before every test."""
    _reset_rate_limits()
    yield


@pytest.fixture()
def db_engine():
    # StaticPool ensures all connections from this engine share the SAME
    # in-memory database (critical for SQLite :memory:).
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def client(db_engine):
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def _override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
