from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.ingestion.engine_log_sync import (
    explain_sync_status,
    get_last_sync_result,
    owner_day_window_utc,
)
from app.storage.migrations import run_migrations
from app.storage.postgres import init_db
from app.storage.repositories import SignalRepository

router = APIRouter()


@router.post("/run-migrations")
async def debug_run_migrations(include_schema: bool = False) -> dict:
    """Manually re-run migrations (and optionally schema.sql).

    By default we only run migrations because schema.sql contains CREATE INDEX
    statements that depend on columns added by migrations 002/004 — running it
    against a legacy DB before migrations have caught up will fail.

    Pass `?include_schema=true` to also re-run schema.sql (only useful for
    fresh DBs).
    """
    schema_error: str | None = None
    if include_schema:
        try:
            await init_db()
        except Exception as exc:
            schema_error = str(exc)
    results = await run_migrations()
    ok = all(r.get("status") == "ok" for r in results) and schema_error is None
    return {
        "ok": ok,
        "schema_init_error": schema_error,
        "migrations": results,
    }


@router.get("/sync")
async def debug_sync_status() -> dict:
    now_utc = datetime.now(timezone.utc)
    start_utc, end_utc = owner_day_window_utc(now_utc, settings.owner_timezone)
    repo = SignalRepository()
    today_counts = await repo.get_today_signal_debug_counts(start_utc=start_utc, end_utc=end_utc)
    last_sync_result = get_last_sync_result()

    return {
        "service": settings.service_name,
        "engine_log_sync_enabled": settings.engine_log_sync_enabled,
        "engine_log_source_configured": bool(settings.engine_log_source_url),
        "window": {
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "owner_timezone": settings.owner_timezone,
        },
        "last_sync_result": last_sync_result,
        "today_counts": today_counts,
        "dashboard_empty_reason": explain_sync_status(
            last_sync_result,
            today_counts.get("signal_events_today", 0),
        ),
    }