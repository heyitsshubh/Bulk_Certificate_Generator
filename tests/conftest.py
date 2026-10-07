"""
pytest fixtures shared across all test modules.

Key decisions:
  - A file-based SQLite test database is used so that background tasks that
    create their own engine (process_job) can see the same data. An in-memory
    DB would be invisible to a second engine in a different thread.
  - The app's engine, SessionLocal, and settings.DATABASE_URL are all patched
    to point at the test DB before the app is imported.
  - Tables are created once per session and dropped at the end.
  - The `client` fixture depends on `create_tables` to guarantee ordering.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db

# ---------------------------------------------------------------------------
# Test database — file-based so background tasks see the same data.
# ---------------------------------------------------------------------------

TEST_DB_FILE = "./test_cert_generator.db"
TEST_DB_URL = f"sqlite:///{TEST_DB_FILE}"

_test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=_test_engine
)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Patch the core database module so that anything that imports it
# (including process_job which reads settings.DATABASE_URL) uses the test DB.
# ---------------------------------------------------------------------------

import app.core.database as _db_module  # noqa: E402

_db_module.engine = _test_engine
_db_module.SessionLocal = TestingSessionLocal

# Also patch settings so process_job's create_engine call uses the test DB.
import app.core.config as _cfg_module  # noqa: E402

_real_settings = _cfg_module.get_settings()


class _TestSettings:
    APP_NAME = _real_settings.APP_NAME
    APP_VERSION = _real_settings.APP_VERSION
    DATABASE_URL = TEST_DB_URL
    STORAGE_DIR = _real_settings.STORAGE_DIR
    GENERATOR_TYPE = _real_settings.GENERATOR_TYPE
    MAX_RECIPIENTS_PER_JOB = _real_settings.MAX_RECIPIENTS_PER_JOB


# Override get_settings globally for the test session
_cfg_module.get_settings = lambda: _TestSettings()  # type: ignore[assignment]

# Now import the app (triggers lifespan setup at test-client creation time)
from app.main import app  # noqa: E402

app.dependency_overrides[get_db] = override_get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Create all tables once for the test session using the test engine."""
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)
    _test_engine.dispose()
    # Remove the test DB file
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass


@pytest.fixture()
def db():
    """Yield a DB session for direct repository use in tests."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(create_tables):  # depends on create_tables so tables exist first
    """Synchronous TestClient for the FastAPI app."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def valid_job_payload() -> dict:
    """A minimal valid job request payload."""
    return {
        "event_name": "Python Bootcamp 2026",
        "issuer": "Acme Corp",
        "recipients": [
            {"full_name": "Alice Smith", "email": "alice@example.com"},
            {"full_name": "Bob Jones",   "email": "bob@example.com"},
        ],
    }
