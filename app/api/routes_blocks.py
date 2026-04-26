from __future__ import annotations

from fastapi import APIRouter

from app.storage.repositories import SignalRepository

router = APIRouter()


@router.get("/active")
async def active_blocks():
    repo = SignalRepository()
    blocks = await repo.get_active_blocks()
    return {"count": len(blocks), "blocks": blocks}


@router.get("/history")
async def block_history(symbol: str | None = None, limit: int = 50):
    repo = SignalRepository()
    blocks = await repo.get_block_history(symbol=symbol, limit=limit)
    return {"count": len(blocks), "blocks": blocks}
