from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.ingestion.engine_log_sync import utc_day_bounds

from app.storage.repositories import SignalRepository

router = APIRouter()


@router.get("/latest")
async def latest_signals(limit: int = 20, bucket: str = "all"):
    repo = SignalRepository()
    normalized_bucket = bucket.lower()
    if normalized_bucket not in {"all", "failed", "radar", "priority", "active"}:
        normalized_bucket = "all"
    observations = await repo.get_latest_pressure_observations(
        limit=limit,
        bucket=normalized_bucket,
    )
    return {
        "deployment_environment": settings.deployment_environment.upper(),
        "observer_mode": settings.observer_mode.upper(),
        "observer_authority": settings.observer_authority.upper(),
        "containment_profile": "PHASE1_OBSERVE_ONLY",
        "count": len(observations),
        "bucket": normalized_bucket,
        "observations": observations,
    }


@router.get("/history")
async def signal_history(symbol: str | None = None, limit: int = 50):
    repo = SignalRepository()
    rows = await repo.get_signal_history(symbol=symbol, limit=limit)
    return {
        "count": len(rows),
        "history_type": "raw_blocks",
        "symbol": symbol,
        "signals": rows,
    }


@router.get("/series")
async def signal_series(symbol: str | None = None, limit: int = 50):
    repo = SignalRepository()
    rows = await repo.get_signal_series(symbol=symbol, limit=limit)
    return {
        "count": len(rows),
        "history_type": "merged_pressure_series",
        "symbol": symbol,
        "signals": rows,
    }


@router.get("/engine-logs/daily")
async def engine_logs_daily(date: str | None = None):
    repo = SignalRepository()
    if date:
        day = datetime.fromisoformat(date).date()
    else:
        day = datetime.now(timezone.utc).date()

    start_utc, end_utc = utc_day_bounds(day)
    summary = await repo.get_engine_logs_daily_summary(start_utc=start_utc, end_utc=end_utc)
    return {
        "date": day.isoformat(),
        "view_mode": "PHASE1_UTC_DAILY_REPORT",
        "window": {
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "window_rule": "[start_utc, end_utc)",
            "owner_timezone": settings.owner_timezone,
        },
        **summary,
    }
