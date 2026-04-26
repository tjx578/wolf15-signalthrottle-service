from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class OHLCCache:
    """Simple in-memory cache for OHLC data keyed by (symbol, timeframe)."""

    def __init__(self, ttl_seconds: int = 300):
        self._store: dict[str, tuple[datetime, list[dict]]] = {}
        self._ttl = ttl_seconds

    def _key(self, symbol: str, timeframe: str) -> str:
        return f"{symbol}:{timeframe}"

    def get(self, symbol: str, timeframe: str) -> list[dict] | None:
        key = self._key(symbol, timeframe)
        entry = self._store.get(key)
        if entry is None:
            return None
        cached_at, data = entry
        age = (datetime.now(timezone.utc) - cached_at).total_seconds()
        if age > self._ttl:
            del self._store[key]
            return None
        return data

    def put(self, symbol: str, timeframe: str, data: list[dict]) -> None:
        key = self._key(symbol, timeframe)
        self._store[key] = (datetime.now(timezone.utc), data)


# Singleton
ohlc_cache = OHLCCache()
