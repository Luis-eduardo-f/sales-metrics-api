"""SQLAlchemy engine/session setup.

The engine is created once, at import time, from `DATABASE_URL` (see `app.config`). It works
unmodified against SQLite (the zero-setup local default) and PostgreSQL (the docker-compose /
production target) -- the rest of the codebase deliberately avoids any dialect-specific SQL
(no `PRAGMA`, no `RETURNING`-only tricks, no Postgres-only types) so switching the connection
string is the only thing required to move between them.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

settings = get_settings()


def _build_engine():
    url = settings.database_url
    connect_args = {}
    engine_kwargs = {}

    if url.startswith("sqlite"):
        # Needed because SQLite objects created in one thread can only be used in that
        # same thread by default; the test suite and FastAPI's threaded test client both
        # need to share a connection across threads.
        connect_args["check_same_thread"] = False

        if ":memory:" in url:
            # An in-memory SQLite database is destroyed as soon as its connection closes.
            # StaticPool keeps a single connection alive for the lifetime of the engine so
            # that every session (and every test) sees the same in-memory database.
            engine_kwargs["poolclass"] = StaticPool

    return create_engine(url, connect_args=connect_args, **engine_kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base class shared by every ORM model."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and always closes it afterwards."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables that don't exist yet.

    Suitable for a demo/portfolio project and for tests. A production system with evolving
    schemas would use a migration tool (e.g. Alembic) instead -- see README.
    """

    # Import models so they are registered on Base.metadata before create_all runs.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
