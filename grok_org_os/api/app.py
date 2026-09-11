"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from grok_org_os import __version__
from grok_org_os.api.routes import agents, channels, messages, orgs, tasks, teams
from grok_org_os.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
