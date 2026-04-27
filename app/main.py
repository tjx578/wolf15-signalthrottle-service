from __future__ import annotations

import asyncio
import logging
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes_blocks import router as blocks_router
from app.api.routes_debug import router as debug_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_health import router as health_router
from app.api.routes_market import router as market_router
from app.api.routes_replay import router as replay_router
from app.api.routes_signals import router as signals_router
from app.api.routes_webhook import router as webhook_router
from app.lifecycle import lifespan

logger = logging.getLogger(__name__)

try:
    from app.api.routes_outcomes import router as outcomes_router
    OUTCOMES_AVAILABLE = True
except Exception:
    outcomes_router = None
    OUTCOMES_AVAILABLE = False
    logger.exception("Outcomes module disabled during startup")


if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def create_app() -> FastAPI:
    app = FastAPI(
        title="Wolf15 SignalThrottle Service",
        version="0.1.0",
        description="Pressure intelligence dashboard for Wolf15 SignalThrottle logs.",
        lifespan=lifespan,
    )

    app.mount("/static", StaticFiles(directory="app/dashboard/static"), name="static")

    # Dashboard at root
    app.include_router(dashboard_router, tags=["dashboard"])

    # API routes
    app.include_router(health_router, tags=["health"])
    app.include_router(debug_router, prefix="/debug", tags=["debug"])
    app.include_router(webhook_router, prefix="/webhook", tags=["webhook"])
    app.include_router(replay_router, prefix="/replay", tags=["replay"])
    app.include_router(signals_router, prefix="/signals", tags=["signals"])
    app.include_router(blocks_router, prefix="/blocks", tags=["blocks"])
    app.include_router(market_router, prefix="/market", tags=["market"])
    if OUTCOMES_AVAILABLE and outcomes_router is not None:
        app.include_router(outcomes_router, prefix="/outcomes", tags=["outcomes"])

    return app


app = create_app()
