from __future__ import annotations

from app.models.log_event import LogEvent


def split_blocks(
    events: list[LogEvent],
    max_gap_seconds: int = 300,
) -> list[list[LogEvent]]:
    """Split a flat list of events into pressure blocks.

    Two consecutive events belong to the same block when they share
    the same symbol and the gap between them is <= *max_gap_seconds*.
    """
    if not events:
        return []

    events = sorted(events, key=lambda e: e.timestamp_utc)
    blocks: list[list[LogEvent]] = []
    current: list[LogEvent] = [events[0]]

    for event in events[1:]:
        prev = current[-1]
        gap = (event.timestamp_utc - prev.timestamp_utc).total_seconds()

        if event.symbol == prev.symbol and gap <= max_gap_seconds:
            current.append(event)
        else:
            blocks.append(current)
            current = [event]

    blocks.append(current)
    return blocks
