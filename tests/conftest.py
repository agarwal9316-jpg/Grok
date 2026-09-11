"""Pytest fixtures — isolated SQLite + TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from grok_org_os import db as db_module
from grok_org_os.api.app import create_app
from grok_org_os.api.deps import get_db
from grok_org_os.db import Base, init_db
from grok_org_os.llm import LLMClient, set_llm_client
from grok_org_os.runtime import AgentRuntime, set_runtime


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
    set_runtime(AgentRuntime(llm=client))
    yield client
    set_llm_client(None)
    set_runtime(None)


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


@pytest.fixture(autouse=True)
def autouse_reset_llm_env(monkeypatch, tmp_path, request):
    """Keep settings/API key isolated: point .env at a temp file and clear key."""
    import os
    from grok_org_os.api.routes import system as system_routes
    from grok_org_os.config import reset_settings_cache
    from grok_org_os.llm import set_llm_client

    env_file = tmp_path / "test.env"
    env_file.write_text(
        "OPENAI_API_KEY=\nOPENAI_BASE_URL=https://api.openai.com/v1\nOPENAI_MODEL=gpt-4o-mini\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(system_routes, "ENV_PATH", env_file)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    # Also clear any process env pollution from prior runs
    for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        os.environ[k] = os.environ.get(k, "")
    reset_settings_cache()
    set_llm_client(None)
    yield
    reset_settings_cache()
    set_llm_client(None)
