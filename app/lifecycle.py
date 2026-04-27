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

try:
    from app.outcomes.outcome_worker import OutcomeWorker
    _OUTCOMES_AVAILABLE = True
except Exception:
    OutcomeWorker = None  # type: ignore[assignment]
    _OUTCOMES_AVAILABLE = False
    logger.exception("Outcome worker disabled during startup")


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


async def outcome_loop(stop_event: asyncio.Event) -> None:
    worker = OutcomeWorker()

    while not stop_event.is_set():
        try:
            await worker.process_due_outcomes()
        except Exception as exc:
            logger.exception("Outcome loop failed: %s", exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logger.info("Starting wolf15-signalthrottle-service")
    stop_event = asyncio.Event()
    finalizer_task: asyncio.Task[None] | None = None
    outcome_task: asyncio.Task[None] | None = None

    try:
        await init_db()
        await run_migrations()
        logger.info("Database ready")
    except Exception as exc:
        logger.warning("DB init skipped (will retry on first request): %s", exc)

    finalizer_task = asyncio.create_task(finalizer_loop(stop_event))
    if _OUTCOMES_AVAILABLE and OutcomeWorker is not None:
        outcome_task = asyncio.create_task(outcome_loop(stop_event))

    yield

    stop_event.set()
    for task in (finalizer_task, outcome_task):
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    await close_db()
    logger.info("Shutdown complete")
