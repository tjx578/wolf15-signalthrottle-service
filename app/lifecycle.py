from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from contextlib import suppress
from typing import AsyncIterator

from fastapi import FastAPI

from app.detector.finalizer import SignalFinalizer
from app.ingestion.engine_log_sync import EngineLogSync, set_last_sync_result
from app.logging_config import setup_logging
from app.storage.postgres import close_db, init_db
from app.storage.migrations import run_migrations
from app.config import settings

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


async def engine_log_sync_loop(stop_event: asyncio.Event) -> None:
    syncer = EngineLogSync()

    while not stop_event.is_set():
        try:
            result = await syncer.sync_today()
            if result.get("status") == "ok" and result.get("events_stored"):
                logger.info(
                    "Engine log sync stored %s new events (%s duplicates)",
                    result.get("events_stored"),
                    result.get("duplicates_skipped"),
                )
        except Exception as exc:
            set_last_sync_result({"status": "error", "error": str(exc)})
            logger.exception("Engine log sync loop failed: %s", exc)

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.engine_log_sync_interval_seconds,
            )
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.assert_observe_only_runtime()
    setup_logging()
    logger.info("Starting wolf15-signalthrottle-service in PHASE1_OBSERVE_ONLY")
    stop_event = asyncio.Event()
    finalizer_task: asyncio.Task[None] | None = None
    engine_log_sync_task: asyncio.Task[None] | None = None

    try:
        schema_error: Exception | None = None
        try:
            await init_db()
        except Exception as exc:
            schema_error = exc
            logger.warning(
                "Database schema init failed; continuing with additive migrations: %s",
                exc,
            )

        migration_results = await run_migrations()
        migration_errors = [r for r in migration_results if r.get("status") != "ok"]
        if migration_errors:
            logger.warning("Database startup completed with migration errors")
        elif schema_error is not None:
            logger.info("Database ready after recovering from schema init failure")
        else:
            logger.info("Database ready")
    except Exception as exc:
        logger.warning("DB init skipped (will retry on first request): %s", exc)

    finalizer_task = asyncio.create_task(finalizer_loop(stop_event))
    if settings.engine_log_sync_enabled:
        engine_log_sync_task = asyncio.create_task(engine_log_sync_loop(stop_event))

    yield

    stop_event.set()
    for task in (finalizer_task, engine_log_sync_task):
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    await close_db()
    logger.info("Shutdown complete")
