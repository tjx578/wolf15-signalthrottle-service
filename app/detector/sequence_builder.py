from __future__ import annotations

from collections import defaultdict

from app.models.log_event import LogEvent


def group_by_symbol(events: list[LogEvent]) -> dict[str, list[LogEvent]]:
    """Group events by symbol and sort each group by timestamp."""
    groups: dict[str, list[LogEvent]] = defaultdict(list)
    for e in events:
        groups[e.symbol].append(e)
    for sym in groups:
        groups[sym].sort(key=lambda e: e.timestamp_utc)
    return dict(groups)
