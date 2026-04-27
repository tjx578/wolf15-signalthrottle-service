from __future__ import annotations

from fastapi import APIRouter

from app.storage.repositories import SignalRepository

router = APIRouter()


@router.get("/latest")
async def latest_signals(limit: int = 20, bucket: str = "all"):
    repo = SignalRepository()
    normalized_bucket = bucket.lower()
    if normalized_bucket not in {"all", "failed", "radar", "watchlist", "ready", "highlighted", "actionable", "priority"}:
        normalized_bucket = "all"
    plans = await repo.get_latest_signals(limit=limit, bucket=normalized_bucket)
    return {"count": len(plans), "bucket": normalized_bucket, "signals": plans}


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


@router.get("/{signal_id}")
async def signal_detail(signal_id: int):
    repo = SignalRepository()
    signal = await repo.get_trade_plan(signal_id)

    if not signal:
        return {
            "status": "not_found",
            "signal_id": signal_id,
        }

    return signal
