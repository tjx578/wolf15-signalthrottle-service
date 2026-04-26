from datetime import datetime, timezone

from app.parser.timestamp_mapper import to_chart_time, to_wita


def test_to_wita():
    ts = datetime(2026, 4, 24, 2, 30, 0, tzinfo=timezone.utc)
    result = to_wita(ts)
    assert result == "2026-04-24 10:30:00"  # UTC+8


def test_to_chart_time():
    ts = datetime(2026, 4, 24, 2, 30, 0, tzinfo=timezone.utc)
    result = to_chart_time(ts, chart_offset_hours=3)
    assert result == "2026-04-24 05:30:00"  # UTC+3


def test_naive_timestamp():
    ts = datetime(2026, 4, 24, 2, 30, 0)  # naive
    result = to_wita(ts)
    assert "10:30:00" in result  # should still convert as UTC
