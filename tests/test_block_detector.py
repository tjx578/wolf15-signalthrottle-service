from datetime import datetime, timedelta, timezone

from app.detector.block_detector import split_blocks
from app.models.log_event import LogEvent


def _make_event(symbol: str, offset_seconds: int) -> LogEvent:
    base = datetime(2026, 4, 24, 2, 0, 0, tzinfo=timezone.utc)
    return LogEvent(
        symbol=symbol,
        timestamp_utc=base + timedelta(seconds=offset_seconds),
        raw_message=f"[SignalThrottle] {symbol} THROTTLED — 3 signals in last 300s (max 3)",
    )


def test_single_block():
    events = [_make_event("USDJPY", i * 5) for i in range(10)]
    blocks = split_blocks(events)
    assert len(blocks) == 1
    assert len(blocks[0]) == 10


def test_split_by_gap():
    events = [
        _make_event("USDJPY", 0),
        _make_event("USDJPY", 5),
        _make_event("USDJPY", 10),
        # Gap > 300s
        _make_event("USDJPY", 600),
        _make_event("USDJPY", 605),
    ]
    blocks = split_blocks(events, max_gap_seconds=300)
    assert len(blocks) == 2
    assert len(blocks[0]) == 3
    assert len(blocks[1]) == 2


def test_split_by_symbol():
    events = [
        _make_event("USDJPY", 0),
        _make_event("USDJPY", 5),
        _make_event("NZDCHF", 10),
        _make_event("NZDCHF", 15),
    ]
    blocks = split_blocks(events)
    assert len(blocks) == 2
    assert len(blocks[0]) == 2
    assert len(blocks[1]) == 2


def test_empty_events():
    blocks = split_blocks([])
    assert blocks == []


def test_single_event():
    events = [_make_event("USDJPY", 0)]
    blocks = split_blocks(events)
    assert len(blocks) == 1
    assert len(blocks[0]) == 1
