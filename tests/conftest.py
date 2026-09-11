"""Pytest fixtures — isolated SQLite + TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from grok_org_os import db as db_module
from grok_org_os.api.app import create_app
from grok_org_os.api.deps import get_db
from grok_org_os.db import Base, init_db
from grok_org_os.llm import LLMClient, set_llm_client


@pytest.fixture()
def db_engine(tmp_path):
    """Fresh SQLite file per test for isolation."""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    init_db(url)
    yield db_module.engine
    Base.metadata.drop_all(bind=db_module.engine)


@pytest.fixture()
def db(db_engine):
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def mock_llm():
    client = LLMClient(api_key="")  # force mock
    set_llm_client(client)
    yield client
    set_llm_client(None)


@pytest.fixture()
def client(db_engine, mock_llm):
    app = create_app()

    def _override_db():
        session = db_module.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_db

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
