from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import BaseModel


SIGNAL_RE = re.compile(
    r"\[SignalThrottle\]\s+(?P<symbol>[A-Z]{6})\s+THROTTLED\s+[—–-]\s+"
    r"(?P<count>\d+)\s+signals\s+in\s+last\s+(?P<window>\d+)s"
)


class ParsedSignalThrottle(BaseModel):
    symbol: str
    timestamp_utc: datetime
    count: int
    window_seconds: int
    raw_message: str


def parse_signalthrottle(
    raw_message: str,
    timestamp_utc: datetime,
) -> ParsedSignalThrottle | None:
    match = SIGNAL_RE.search(raw_message)
    if not match:
        return None

    ts = timestamp_utc
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    return ParsedSignalThrottle(
        symbol=match.group("symbol"),
        timestamp_utc=ts,
        count=int(match.group("count")),
        window_seconds=int(match.group("window")),
        raw_message=raw_message,
    )
