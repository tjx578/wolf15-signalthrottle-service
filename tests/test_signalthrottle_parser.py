from datetime import datetime, timezone

from app.parser.signalthrottle_parser import parse_signalthrottle


def test_parse_standard_message():
    msg = "[SignalThrottle] USDJPY THROTTLED — 3 signals in last 300s (max 3)"
    ts = datetime(2026, 4, 24, 2, 30, 34, tzinfo=timezone.utc)

    result = parse_signalthrottle(msg, ts)

    assert result is not None
    assert result.symbol == "USDJPY"
    assert result.count == 3
    assert result.window_seconds == 300
    assert result.timestamp_utc == ts


def test_parse_different_symbol():
    msg = "[SignalThrottle] NZDCHF THROTTLED — 3 signals in last 300s (max 3)"
    ts = datetime(2026, 4, 24, 3, 0, 0, tzinfo=timezone.utc)

    result = parse_signalthrottle(msg, ts)

    assert result is not None
    assert result.symbol == "NZDCHF"


def test_parse_with_surrounding_text():
    msg = "2026-04-24T02:30:34.104925Z WARNING [SignalThrottle] CADCHF THROTTLED — 3 signals in last 300s (max 3)"
    ts = datetime(2026, 4, 24, 2, 30, 34, tzinfo=timezone.utc)

    result = parse_signalthrottle(msg, ts)

    assert result is not None
    assert result.symbol == "CADCHF"


def test_parse_no_match():
    msg = "Some random log line without signal throttle"
    ts = datetime(2026, 4, 24, 2, 30, 34, tzinfo=timezone.utc)

    result = parse_signalthrottle(msg, ts)
    assert result is None


def test_parse_naive_timestamp_gets_utc():
    msg = "[SignalThrottle] EURUSD THROTTLED — 3 signals in last 300s (max 3)"
    ts = datetime(2026, 4, 24, 2, 30, 34)  # naive

    result = parse_signalthrottle(msg, ts)

    assert result is not None
    assert result.timestamp_utc.tzinfo is not None


def test_parse_dash_variants():
    """The regex should handle em-dash, en-dash, and regular dash."""
    for dash in ["—", "–", "-"]:
        msg = f"[SignalThrottle] GBPUSD THROTTLED {dash} 3 signals in last 300s (max 3)"
        ts = datetime(2026, 4, 24, 2, 30, 34, tzinfo=timezone.utc)
        result = parse_signalthrottle(msg, ts)
        assert result is not None, f"Failed for dash: {repr(dash)}"
        assert result.symbol == "GBPUSD"
