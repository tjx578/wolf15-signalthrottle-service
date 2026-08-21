from __future__ import annotations

import asyncio
import sys

from fastapi import Depends, FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.api.routes_blocks import router as blocks_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_health import router as health_router
from app.api.routes_owner import router as owner_router
from app.api.routes_signals import router as signals_router
from app.api.routes_webhook import router as webhook_router
from app.api.auth import require_dashboard_auth
from app.config import settings
from app.lifecycle import lifespan


if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def create_app() -> FastAPI:
    settings.assert_observe_only_runtime()
    app = FastAPI(
        title="Wolf15 Pressure Observatory",
        version="0.2.0",
        description=(
            "Observational-only pressure evidence and owner console. "
            "This service has no strategy, risk, command, or execution authority."
        ),
        lifespan=lifespan,
    )

    app.mount("/static", StaticFiles(directory="app/dashboard/static"), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    # Dashboard at root
    app.include_router(dashboard_router, tags=["dashboard"])

    # API routes
    app.include_router(health_router, tags=["health"])
    app.include_router(webhook_router, prefix="/webhook", tags=["webhook"])
    owner_dependencies = [Depends(require_dashboard_auth)]
    app.include_router(
        signals_router,
        prefix="/signals",
        tags=["signals"],
        dependencies=owner_dependencies,
    )
    app.include_router(
        blocks_router,
        prefix="/blocks",
        tags=["blocks"],
        dependencies=owner_dependencies,
    )
    app.include_router(
        owner_router,
        prefix="/api/v1/owner",
        tags=["owner-read-models"],
        dependencies=owner_dependencies,
    )

    return app


app = create_app()
