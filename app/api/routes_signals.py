from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.storage.repositories import SignalRepository

router = APIRouter()


@router.get("/latest")
async def latest_signals(limit: int = 20):
    repo = SignalRepository()
    plans = await repo.get_latest_trade_plans(limit=limit)
    return {"count": len(plans), "signals": plans}


@router.get("/{signal_id}")
async def signal_detail(signal_id: int):
    repo = SignalRepository()
    plan = await repo.get_trade_plan(signal_id)
    if not plan:
        raise HTTPException(status_code=404, detail="signal not found")
    return plan
