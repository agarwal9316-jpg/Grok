"""SQLAlchemy engine and session helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from grok_org_os.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str | None = None):
    database_url = url or get_settings().database_url
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(database_url, connect_args=connect_args)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ARG001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def init_db(url: str | None = None) -> None:
    """Create all tables. Optionally rebind engine for tests."""
    global engine, SessionLocal
    if url is not None:
        engine = _make_engine(url)
        SessionLocal = sessionmaker(
            bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
    from grok_org_os import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_db_for_tests(url: str = "sqlite:///:memory:") -> Session:
    """Drop and recreate schema for isolated tests."""
    global engine, SessionLocal
    Base.metadata.drop_all(bind=engine) if engine else None
    engine = _make_engine(url)
    SessionLocal = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    from grok_org_os import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    return SessionLocal()
