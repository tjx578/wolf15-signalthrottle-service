from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.ingestion.engine_log_sync import (
    explain_sync_status,
    get_last_sync_result,
    owner_day_window_utc,
)
from app.storage.repositories import SignalRepository

router = APIRouter()


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