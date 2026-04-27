from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from contextlib import suppress
from typing import AsyncIterator

from fastapi import FastAPI

from app.detector.finalizer import SignalFinalizer
from app.logging_config import setup_logging
from app.storage.postgres import close_db, init_db
from app.storage.migrations import run_migrations

logger = logging.getLogger(__name__)


async def finalizer_loop(stop_event: asyncio.Event) -> None:
    finalizer = SignalFinalizer()

    while not stop_event.is_set():
        try:
            await finalizer.finalize_due_blocks()
        except Exception as exc:
            logger.exception("Finalizer loop failed: %s", exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=10)
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logger.info("Starting wolf15-signalthrottle-service")
    stop_event = asyncio.Event()
    finalizer_task: asyncio.Task[None] | None = None

    try:
        await init_db()
        await run_migrations()
        logger.info("Database ready")
    except Exception as exc:
        logger.warning("DB init skipped (will retry on first request): %s", exc)

    finalizer_task = asyncio.create_task(finalizer_loop(stop_event))

    yield

    stop_event.set()
    if finalizer_task is not None:
        finalizer_task.cancel()
        with suppress(asyncio.CancelledError):
            await finalizer_task

    await close_db()
    logger.info("Shutdown complete")
