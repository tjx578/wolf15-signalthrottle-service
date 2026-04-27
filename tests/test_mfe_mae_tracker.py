from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.outcomes.mfe_mae_tracker import (
    MFEMAETracker,
    calculate_mfe_mae,
    infer_direction,
    pip_size,
    window_candles,
)


def _candle(ts, high, low, close=None, open_=None):
    return {
        "timestamp": ts,
        "open": open_ if open_ is not None else low,
        "high": high,
        "low": low,
        "close": close if close is not None else high,
    }


def test_pip_size():
    assert pip_size("USDJPY") == 0.01
    assert pip_size("EURUSD") == 0.0001


def test_infer_direction():
    assert infer_direction("BUY_CONTINUATION") == "BUY"
    assert infer_direction("SELL_REJECTION_OR_EXIT_LONG") == "SELL"
    assert infer_direction("NO_TRADE_WAIT_CONTEXT") == "NEUTRAL"
    assert infer_direction(None) == "NEUTRAL"


def test_window_candles_filters_by_time():
    start = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    candles = [
        _candle(start - timedelta(minutes=5), 1.1, 1.0),
        _candle(start + timedelta(minutes=5), 1.1, 1.0),
        _candle(start + timedelta(minutes=20), 1.1, 1.0),
        _candle(start + timedelta(minutes=40), 1.1, 1.0),
    ]
    out = window_candles(candles, start, 30)
    assert len(out) == 2


def test_calculate_mfe_mae_buy():
    start = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    candles = [
        _candle(start + timedelta(minutes=5), high=105, low=98, close=104),
        _candle(start + timedelta(minutes=20), high=103, low=99, close=102),
    ]
    mfe, mae, last_close = calculate_mfe_mae(
        symbol="EURUSD",
        execution_side="BUY_CONTINUATION",
        entry_price=100,
        candles=candles,
        signal_end_utc=start,
        minutes=30,
    )
    assert mfe == 5
    assert mae == 2
    assert last_close == 102


def test_calculate_mfe_mae_sell():
    start = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    candles = [
        _candle(start + timedelta(minutes=5), high=102, low=95, close=96),
    ]
    mfe, mae, last_close = calculate_mfe_mae(
        symbol="EURUSD",
        execution_side="SELL_REJECTION_OR_EXIT_LONG",
        entry_price=100,
        candles=candles,
        signal_end_utc=start,
        minutes=30,
    )
    assert mfe == 5
    assert mae == 2
    assert last_close == 96


def test_calculate_mfe_mae_no_data():
    start = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    mfe, mae, last_close = calculate_mfe_mae(
        symbol="EURUSD",
        execution_side="BUY_CONTINUATION",
        entry_price=100,
        candles=[],
        signal_end_utc=start,
        minutes=30,
    )
    assert mfe is None and mae is None and last_close is None


class _FakeOhlc:
    def __init__(self, candles):
        self._candles = candles

    async def fetch(self, symbol, timeframe, bars=80, end_time_utc=None):
        return list(self._candles)


def test_tracker_evaluate_strong_follow_through_buy():
    start = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    candles = [
        _candle(start + timedelta(minutes=5), high=160.05, low=159.78, close=160.00),
        _candle(start + timedelta(minutes=20), high=160.10, low=159.82, close=160.05),
        _candle(start + timedelta(minutes=45), high=160.15, low=159.90, close=160.10),
    ]
    tracker = MFEMAETracker(_FakeOhlc(candles))
    plan = {
        "id": 1,
        "symbol": "USDJPY",
        "pressure_grade": "A",
        "execution_grade": "A",
        "execution_side": "BUY_CONTINUATION",
        "payload": {
            "signal_end_utc": start.isoformat(),
            "price_at_signal_end": 159.80,
            "chart_phase": "PIVOT_RECLAIM_CONTINUATION",
        },
    }
    result = asyncio.run(tracker.evaluate(plan))
    assert result["price_at_signal"] == 159.80
    assert result["mfe_30m"] == pytest.approx(160.10 - 159.80)
    assert result["mae_30m"] == pytest.approx(159.80 - 159.78)
    assert result["result_label"] == "FOLLOW_THROUGH_STRONG"
    assert result["chart_phase"] == "PIVOT_RECLAIM_CONTINUATION"


def test_tracker_evaluate_neutral_direction():
    start = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    tracker = MFEMAETracker(_FakeOhlc([_candle(start + timedelta(minutes=5), 1.1, 1.0)]))
    plan = {
        "id": 2,
        "symbol": "EURUSD",
        "execution_side": "NO_TRADE_WAIT_CONTEXT",
        "payload": {
            "signal_end_utc": start.isoformat(),
            "price_at_signal_end": 1.05,
        },
    }
    result = asyncio.run(tracker.evaluate(plan))
    assert result["result_label"] == "PENDING_DIRECTIONAL_CONFIRMATION"


def test_tracker_evaluate_missing_price():
    start = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    tracker = MFEMAETracker(_FakeOhlc([]))
    plan = {
        "id": 3,
        "symbol": "EURUSD",
        "execution_side": "BUY_CONTINUATION",
        "payload": {"signal_end_utc": start.isoformat()},
    }
    result = asyncio.run(tracker.evaluate(plan))
    assert result["result_label"] == "PENDING_NO_PRICE"
