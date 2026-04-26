from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..market.finnhub_client import FinnhubClient

router = APIRouter()


@router.get("/snapshot/{symbol}")
async def market_snapshot_test(symbol: str):
    if not settings.finnhub_api_key:
        raise HTTPException(status_code=400, detail="FINNHUB_API_KEY is not configured")

    client = FinnhubClient(api_key=settings.finnhub_api_key)

    m15 = await client.fetch(symbol, "M15", bars=20, end_time_utc=datetime.now(timezone.utc))
    h1 = await client.fetch(symbol, "H1", bars=20, end_time_utc=datetime.now(timezone.utc))
    h4 = await client.fetch(symbol, "H4", bars=20, end_time_utc=datetime.now(timezone.utc))
    d1 = await client.fetch(symbol, "D1", bars=20, end_time_utc=datetime.now(timezone.utc))

    return {
        "symbol": symbol.upper(),
        "counts": {
            "M15": len(m15),
            "H1": len(h1),
            "H4": len(h4),
            "D1": len(d1),
        },
        "latest": {
            "M15": m15[-1] if m15 else None,
            "H1": h1[-1] if h1 else None,
            "H4": h4[-1] if h4 else None,
            "D1": d1[-1] if d1 else None,
        },
    }
