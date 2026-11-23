"""SQLAlchemy engine / session management (SQLite by default)."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


def _init_engine():
    global _engine, _SessionLocal
    url = get_settings().resolved_database_url
    if url.startswith("sqlite"):
        _engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    else:
        # serverless instances are short-lived: don't keep idle pooled connections
        from sqlalchemy.pool import NullPool

        _engine = create_engine(url, poolclass=NullPool, pool_pre_ping=True, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)

    # Create tables on first use (serverless runtimes may not run the ASGI lifespan).
    from app import models  # noqa: F401

    Base.metadata.create_all(_engine)


def get_engine():
    if _engine is None:
        _init_engine()
    return _engine


def init_db() -> None:
    from app import models  # noqa: F401  (register models)

    Base.metadata.create_all(get_engine())


def reset_engine() -> None:
    """Dispose the engine (used by tests when settings change)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    get_engine()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    get_engine()
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
