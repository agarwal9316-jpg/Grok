"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from grok_org_os import __version__
from grok_org_os import db as db_module
from grok_org_os.api.routes import agents, channels, messages, orgs, system, tasks, teams
from grok_org_os.bootstrap import bootstrap_sample_org
from grok_org_os.models import Organisation

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_module.init_db()
    # Auto-bootstrap sample org on first launch if empty.
    # Use db_module.SessionLocal so tests that rebind the engine are respected.
    db = db_module.SessionLocal()
    try:
        if db.query(Organisation).count() == 0:
            bootstrap_sample_org(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Grok Org OS",
        description="Portable multi-agent AI organization platform",
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(orgs.router, prefix="/api")
    app.include_router(teams.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(channels.router, prefix="/api")
    app.include_router(messages.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(system.router, prefix="/api")

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
