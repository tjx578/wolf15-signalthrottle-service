from datetime import datetime, timedelta, timezone

from app.models.log_event import LogEvent
from app.scoring.pressure_metrics import calculate_pressure_metrics


def _make_events(count: int, gap_seconds: float = 5.0) -> list[LogEvent]:
    base = datetime(2026, 4, 24, 2, 0, 0, tzinfo=timezone.utc)
    return [
        LogEvent(
            symbol="USDJPY",
            timestamp_utc=base + timedelta(seconds=i * gap_seconds),
            raw_message="test",
        )
        for i in range(count)
    ]


def test_basic_metrics():
    events = _make_events(10, gap_seconds=5)
    m = calculate_pressure_metrics(events)

    assert m["event_count"] == 10
    assert m["duration_minutes"] == 0.75  # 45s / 60
    assert m["avg_gap_seconds"] == 5.0
    assert m["max_gap_seconds"] == 5.0
    assert m["density_per_minute"] > 10


def test_single_event():
    events = _make_events(1)
    m = calculate_pressure_metrics(events)
    assert m["event_count"] == 1
    assert m["duration_minutes"] == 0.0
    assert m["avg_gap_seconds"] is None


def test_variable_gaps():
    base = datetime(2026, 4, 24, 2, 0, 0, tzinfo=timezone.utc)
    events = [
        LogEvent(symbol="USDJPY", timestamp_utc=base, raw_message="t"),
        LogEvent(symbol="USDJPY", timestamp_utc=base + timedelta(seconds=10), raw_message="t"),
        LogEvent(symbol="USDJPY", timestamp_utc=base + timedelta(seconds=60), raw_message="t"),
    ]
    m = calculate_pressure_metrics(events)
    assert m["max_gap_seconds"] == 50.0
    assert m["avg_gap_seconds"] == 30.0
