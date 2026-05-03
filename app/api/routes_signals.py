from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.ingestion.engine_log_sync import utc_day_bounds

from app.storage.repositories import SignalRepository

router = APIRouter()


def _public_signal_contract(row: dict) -> dict:
    payload = row.get("payload") or {}
    snapshot = payload.get("snapshot") or {}
    chain_context = payload.get("chain_context") or {}
    public_row = dict(row)
    public_row["h4_structure"] = row.get("h4_structure") or snapshot.get("h4_structure")
    public_row["h4_context_type"] = row.get("h4_context_type") or snapshot.get("h4_context_type")
    public_row["standalone_grade"] = row.get("standalone_grade") or chain_context.get("standalone_grade")
    public_row["chain_adjusted_grade"] = row.get("chain_adjusted_grade") or chain_context.get("chain_adjusted_grade")
    public_row["chain_type"] = row.get("chain_type") or chain_context.get("chain_type")
    public_row["execution_mode"] = row.get("execution_mode") or chain_context.get("execution_mode")
    public_row["previous_block_grade"] = row.get("previous_block_grade") or chain_context.get("previous_block_grade")
    public_row["previous_block_end_wita"] = row.get("previous_block_end_wita") or chain_context.get("previous_block_end_wita")
    public_row["gap_from_previous_minutes"] = row.get("gap_from_previous_minutes") or chain_context.get("gap_from_previous_minutes")
    return public_row


@router.get("/latest")
async def latest_signals(limit: int = 20, bucket: str = "all"):
    repo = SignalRepository()
    normalized_bucket = bucket.lower()
    if normalized_bucket not in {"all", "failed", "radar", "watchlist", "ready", "highlighted", "actionable", "priority"}:
        normalized_bucket = "all"
    plans = await repo.get_latest_signals(limit=limit, bucket=normalized_bucket)
    public_plans = [_public_signal_contract(plan) for plan in plans]
    return {"count": len(public_plans), "bucket": normalized_bucket, "signals": public_plans}


@router.get("/trade-plans")
async def latest_trade_plans(limit: int = 20, bucket: str = "all"):
    repo = SignalRepository()
    normalized_bucket = bucket.lower()
    if normalized_bucket not in {"all", "watchlist", "actionable"}:
        normalized_bucket = "all"
    plans = await repo.get_latest_trade_plans(limit=limit, bucket=normalized_bucket)
    public_plans = [_public_signal_contract(plan) for plan in plans]
    return {"count": len(public_plans), "bucket": normalized_bucket, "trade_plans": public_plans}


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


@router.get("/{signal_id}")
async def signal_detail(signal_id: int):
    repo = SignalRepository()
    signal = await repo.get_trade_plan(signal_id)

    if not signal:
        return {
            "status": "not_found",
            "signal_id": signal_id,
        }

    return _public_signal_contract(signal)
