"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from grok_org_os import db as db_module


def get_db() -> Generator[Session, None, None]:
    # Look up SessionLocal at call time so test rebinds are visible
    db = db_module.SessionLocal()
    try:
        yield db
    finally:
        db.close()
