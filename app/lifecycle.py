from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.logging_config import setup_logging
from app.storage.postgres import close_db, init_db
from app.storage.migrations import run_migrations

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logger.info("Starting wolf15-signalthrottle-service")

    try:
        await init_db()
        await run_migrations()
        logger.info("Database ready")
    except Exception as exc:
        logger.warning("DB init skipped (will retry on first request): %s", exc)

    yield

    await close_db()
    logger.info("Shutdown complete")
