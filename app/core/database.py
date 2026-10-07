"""
Database engine and session factory setup.

Design:
- The SQLAlchemy engine is created once at import time (effectively a Singleton).
- `get_db()` is a FastAPI dependency that yields a scoped session per HTTP
  request and closes it automatically when the request finishes.
- Background tasks must NOT use this dependency directly — they should call
  `SessionLocal()` directly and manage the lifecycle themselves to remain
  thread-safe.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# SQLite requires check_same_thread=False to allow use from the
# background task thread spawned by FastAPI BackgroundTasks.
_connect_args = (
    {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    # Pool size tuning: SQLite is single-writer, no point in large pools.
    pool_pre_ping=True,
)

SessionLocal: sessionmaker[Session] = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    """Declarative base class shared by all ORM models."""


def get_db():
    """FastAPI dependency: yields a database session for the current request."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
