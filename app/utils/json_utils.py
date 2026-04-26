from __future__ import annotations

import hashlib
from datetime import datetime


def make_event_hash(symbol: str, timestamp_utc: str | datetime, message: str) -> str:
    ts = timestamp_utc.isoformat() if isinstance(timestamp_utc, datetime) else timestamp_utc
    raw = f"{symbol}|{ts}|{message}"
    return hashlib.sha256(raw.encode()).hexdigest()
