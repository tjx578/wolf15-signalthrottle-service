from __future__ import annotations

from fastapi import APIRouter

from app.storage.repositories import SignalRepository

router = APIRouter()


@router.get("/latest")
async def latest_signals(limit: int = 20, bucket: str = "all"):
    repo = SignalRepository()
    normalized_bucket = bucket.lower()
    if normalized_bucket not in {"all", "actionable", "watchlist"}:
        normalized_bucket = "all"
    plans = await repo.get_latest_trade_plans(limit=limit, bucket=normalized_bucket)
    return {"count": len(plans), "bucket": normalized_bucket, "signals": plans}


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
