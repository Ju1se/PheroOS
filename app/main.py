from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.agents import router as agents_router
from app.routes.frontend import STATIC_ROOT
from app.routes.frontend import router as frontend_router
from app.routes.health import router as health_router
from app.routes.platform import router as platform_router
from app.routes.runs import router as runs_router
from app.routes.skills import router as skills_router
from app.routes.tools import router as tools_router
from app.routes.wrds import router as wrds_router


def create_app() -> FastAPI:
    app = FastAPI(title="Local Agent Platform", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
    app.include_router(frontend_router)
    app.include_router(health_router)
    app.include_router(agents_router)
    app.include_router(runs_router)
    app.include_router(platform_router)
    app.include_router(skills_router)
    app.include_router(tools_router)
    app.include_router(wrds_router)
    return app


app = create_app()
