from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.market.finnhub_client import FinnhubClient

router = APIRouter()


@router.get("/snapshot/{symbol}")
async def market_snapshot(symbol: str):
    if not settings.finnhub_api_key:
        raise HTTPException(status_code=503, detail="Finnhub API key not configured")

    client = FinnhubClient(api_key=settings.finnhub_api_key)

    try:
        m15 = await client.fetch(symbol, "M15", bars=20)
        h1 = await client.fetch(symbol, "H1", bars=20)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Finnhub fetch failed: {exc}")

    last_price = m15[-1]["close"] if m15 else (h1[-1]["close"] if h1 else None)

    return {
        "symbol": symbol,
        "last_price": last_price,
        "m15_bars": len(m15),
        "h1_bars": len(h1),
        "m15_latest": m15[-3:] if m15 else [],
        "h1_latest": h1[-3:] if h1 else [],
    }
