from __future__ import annotations

from collections import defaultdict

from ..models.log_event import LogEvent


def group_by_symbol(events: list[LogEvent]) -> dict[str, list[LogEvent]]:
    """Group events by symbol and sort each group by timestamp.

    NOTE: Do NOT use this for canonical block formation. Grouping by symbol
    discards the global chronological ordering and lets a different pair's
    intervention silently disappear, which violates the "pair replacement
    closes the block" rule. Use `build_canonical_sequences` instead.

    This helper is retained only for per-symbol statistics / aggregations.
    """
    groups: dict[str, list[LogEvent]] = defaultdict(list)
    for e in events:
        groups[e.symbol].append(e)
    for sym in groups:
        groups[sym].sort(key=lambda e: e.timestamp_utc)
    return dict(groups)


def build_canonical_sequences(
    events: list[LogEvent],
    max_gap_seconds: int = 300,
) -> list[list[LogEvent]]:
    """Split a global chronological event stream into canonical sequences.

    Rules (golden reference):
      - sort all events by timestamp_utc (stable, global stream)
      - extend the current sequence iff:
          * symbol matches the previous event's symbol, AND
          * gap to previous event <= max_gap_seconds
      - otherwise close the current sequence and start a new one
        (this captures "pair-other muncul → block lama selesai")

    Returns a list of sequences (each a non-empty list of LogEvent).
    """
    if not events:
        return []

    events_sorted = sorted(events, key=lambda e: e.timestamp_utc)
    sequences: list[list[LogEvent]] = []
    current: list[LogEvent] = [events_sorted[0]]

    for event in events_sorted[1:]:
        prev = current[-1]
        gap = (event.timestamp_utc - prev.timestamp_utc).total_seconds()
        if event.symbol == prev.symbol and gap <= max_gap_seconds:
            current.append(event)
        else:
            sequences.append(current)
            current = [event]

    sequences.append(current)
    return sequences


def split_sequence_by_continuity_gap(
    events: list[LogEvent],
    max_gap_seconds: int,
) -> list[list[LogEvent]]:
    """Split a same-symbol canonical sequence into continuity-valid sub-blocks.

    This is intentionally stricter than canonical sequence formation. A gap that
    exceeds the continuity threshold starts a new pressure block, but the blocks
    can still belong to the same higher-level pressure series as long as the
    outer canonical sequence remains intact.
    """
    if not events:
        return []

    events_sorted = sorted(events, key=lambda e: e.timestamp_utc)
    blocks: list[list[LogEvent]] = []
    current: list[LogEvent] = [events_sorted[0]]

    for event in events_sorted[1:]:
        prev = current[-1]
        gap = (event.timestamp_utc - prev.timestamp_utc).total_seconds()
        if gap <= max_gap_seconds:
            current.append(event)
        else:
            blocks.append(current)
            current = [event]

    blocks.append(current)
    return blocks


def make_block_hash(events: list[LogEvent]) -> str:
    """Stable canonical identity for a sequence of events.

    Same sequence of events (symbol + every timestamp) → same hash, so replay
    of the same logs yields idempotent block writes.
    """
    import hashlib

    if not events:
        return ""
    payload = "|".join(
        [
            events[0].symbol,
            events[0].timestamp_utc.isoformat(),
            events[-1].timestamp_utc.isoformat(),
            str(len(events)),
            ",".join(e.timestamp_utc.isoformat() for e in events),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
