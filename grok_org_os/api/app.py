"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from grok_org_os import __version__
from grok_org_os import db as db_module
from grok_org_os.api.routes import (
    agents,
    approvals,
    channels,
    connectors,
    files,
    messages,
    orgs,
    routines,
    system,
    tasks,
    teams,
)
from grok_org_os.bootstrap import bootstrap_sample_org
from grok_org_os.connectors.registry import register_builtins
from grok_org_os.models import Organisation

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_module.init_db()
    register_builtins()
    # Ensure workspace exists
    from grok_org_os.config import get_settings

    get_settings().workspace_path()

    db = db_module.SessionLocal()
    try:
        if db.query(Organisation).count() == 0:
            bootstrap_sample_org(db)
    finally:
        db.close()

    # Start background agent poller + routines scheduler
    from grok_org_os.runtime import get_runtime
    from grok_org_os.scheduler import shutdown_scheduler, start_scheduler

    runtime = get_runtime()
    await runtime.start_background_poller(interval=2.0)
    try:
        start_scheduler()
    except Exception:  # noqa: BLE001
        logger.exception("Scheduler failed to start")

    yield

    runtime.stop()
    try:
        shutdown_scheduler()
    except Exception:  # noqa: BLE001
        pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Grok Org OS",
        description="Portable multi-agent AI organization platform — full power v2",
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(orgs.router, prefix="/api")
    app.include_router(teams.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(channels.router, prefix="/api")
    app.include_router(messages.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(approvals.router, prefix="/api")
    app.include_router(routines.router, prefix="/api")
    app.include_router(connectors.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
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
