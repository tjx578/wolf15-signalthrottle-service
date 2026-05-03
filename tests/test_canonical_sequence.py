from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.detector.sequence_builder import (
    build_canonical_sequences,
    make_block_hash,
    split_sequence_by_continuity_gap,
)
from app.models.log_event import LogEvent


def _ev(symbol: str, ts: datetime) -> LogEvent:
    return LogEvent(
        symbol=symbol,
        event_type="SIGNAL_THROTTLE",
        timestamp_utc=ts,
        raw_message=f"{symbol}@{ts.isoformat()}",
    )


def test_global_sequence_breaks_on_other_symbol_even_if_same_symbol_gap_under_300() -> None:
    """GBPUSD, GBPUSD, EURUSD, GBPUSD, GBPUSD — must yield 3 sequences, not 2.

    Without global ordering, grouping by symbol first would have merged the
    two GBPUSD windows into a single 4-event block.
    """
    base = datetime(2026, 4, 24, 7, 0, 0, tzinfo=timezone.utc)
    events = [
        _ev("GBPUSD", base),
        _ev("GBPUSD", base + timedelta(seconds=60)),
        _ev("EURUSD", base + timedelta(seconds=120)),
        _ev("GBPUSD", base + timedelta(seconds=180)),
        _ev("GBPUSD", base + timedelta(seconds=240)),
    ]

    sequences = build_canonical_sequences(events, max_gap_seconds=300)

    assert len(sequences) == 3
    assert [s[0].symbol for s in sequences] == ["GBPUSD", "EURUSD", "GBPUSD"]
    assert len(sequences[0]) == 2
    assert len(sequences[1]) == 1
    assert len(sequences[2]) == 2


def test_canonical_sequence_splits_on_gap_over_max() -> None:
    base = datetime(2026, 4, 24, 7, 0, 0, tzinfo=timezone.utc)
    events = [
        _ev("USDJPY", base),
        _ev("USDJPY", base + timedelta(seconds=60)),
        _ev("USDJPY", base + timedelta(seconds=400)),  # gap > 300
    ]

    sequences = build_canonical_sequences(events, max_gap_seconds=300)

    assert len(sequences) == 2
    assert len(sequences[0]) == 2
    assert len(sequences[1]) == 1


def test_phase1_canonical_sequence_does_not_split_same_pair_large_gap() -> None:
    base = datetime(2026, 4, 24, 7, 0, 0, tzinfo=timezone.utc)
    events = [
        _ev("USDJPY", base),
        _ev("USDJPY", base + timedelta(seconds=60)),
        _ev("USDJPY", base + timedelta(seconds=400)),
    ]

    sequences = build_canonical_sequences(events, max_gap_seconds=None)

    assert len(sequences) == 1
    assert len(sequences[0]) == 3


def test_canonical_sequence_keeps_single_block_when_gap_under_max() -> None:
    base = datetime(2026, 4, 24, 7, 0, 0, tzinfo=timezone.utc)
    events = [
        _ev("USDJPY", base + timedelta(seconds=i * 30))
        for i in range(5)
    ]

    sequences = build_canonical_sequences(events, max_gap_seconds=300)

    assert len(sequences) == 1
    assert len(sequences[0]) == 5


def test_continuity_gap_splits_sub_blocks_without_changing_canonical_family() -> None:
    base = datetime(2026, 4, 24, 13, 0, 0, tzinfo=timezone.utc)
    events = [
        _ev("NZDCHF", base + timedelta(seconds=offset))
        for offset in (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 240, 250, 260)
    ]

    sequences = build_canonical_sequences(events, max_gap_seconds=300)
    sub_blocks = split_sequence_by_continuity_gap(sequences[0], max_gap_seconds=90)

    assert len(sequences) == 1
    assert len(sub_blocks) == 2
    assert len(sub_blocks[0]) == 10
    assert len(sub_blocks[1]) == 3


def test_block_hash_is_stable_for_same_events() -> None:
    base = datetime(2026, 4, 24, 7, 0, 0, tzinfo=timezone.utc)
    events_a = [_ev("USDJPY", base + timedelta(seconds=i * 30)) for i in range(3)]
    events_b = [_ev("USDJPY", base + timedelta(seconds=i * 30)) for i in range(3)]

    assert make_block_hash(events_a) == make_block_hash(events_b)


def test_block_hash_differs_when_event_count_changes() -> None:
    base = datetime(2026, 4, 24, 7, 0, 0, tzinfo=timezone.utc)
    events_a = [_ev("USDJPY", base + timedelta(seconds=i * 30)) for i in range(3)]
    events_b = events_a + [_ev("USDJPY", base + timedelta(seconds=120))]

    assert make_block_hash(events_a) != make_block_hash(events_b)


def test_block_hash_differs_when_symbol_changes() -> None:
    base = datetime(2026, 4, 24, 7, 0, 0, tzinfo=timezone.utc)
    events_a = [_ev("USDJPY", base + timedelta(seconds=i * 30)) for i in range(3)]
    events_b = [_ev("EURUSD", base + timedelta(seconds=i * 30)) for i in range(3)]

    assert make_block_hash(events_a) != make_block_hash(events_b)
