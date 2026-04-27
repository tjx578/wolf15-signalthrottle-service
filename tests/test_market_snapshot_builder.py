from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.market.market_snapshot_builder import MarketSnapshotBuilder


class FakeFinnhubClient:
    async def fetch(self, symbol: str, timeframe: str, bars: int = 200, end_time_utc=None):
        end_time_utc = end_time_utc or datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)
        step = {
            "M15": timedelta(minutes=15),
            "H1": timedelta(hours=1),
            "H4": timedelta(hours=4),
            "D1": timedelta(days=1),
        }[timeframe]
        candles = []
        base = 159.20 if symbol == "USDJPY" else 1.2700
        for index in range(60):
            close = base + (index * 0.01 if timeframe in {"M15", "H1"} else index * 0.02)
            candles.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": end_time_utc - step * (59 - index),
                    "open": close - 0.02,
                    "high": close + 0.04,
                    "low": close - 0.04,
                    "close": close,
                    "volume": 1000 + index,
                    "source": "fake",
                }
            )
        return candles


class FakePreciseFinnhubClient:
    async def fetch(self, symbol: str, timeframe: str, bars: int = 200, end_time_utc=None):
        del bars
        if timeframe == "M15":
            return [
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": datetime(2026, 4, 23, 9, 30, tzinfo=timezone.utc),
                    "open": 0.46220,
                    "high": 0.46240,
                    "low": 0.46200,
                    "close": 0.46210,
                    "volume": 1000,
                    "source": "fake",
                },
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": datetime(2026, 4, 23, 9, 45, tzinfo=timezone.utc),
                    "open": 0.46210,
                    "high": 0.46220,
                    "low": 0.46180,
                    "close": 0.46192,
                    "volume": 1001,
                    "source": "fake",
                },
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc),
                    "open": 0.46192,
                    "high": 0.46200,
                    "low": 0.46150,
                    "close": 0.46174,
                    "volume": 1002,
                    "source": "fake",
                },
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": datetime(2026, 4, 23, 10, 15, tzinfo=timezone.utc),
                    "open": 0.46174,
                    "high": 0.46190,
                    "low": 0.46120,
                    "close": 0.46130,
                    "volume": 1003,
                    "source": "fake",
                },
            ]

        step = {
            "H1": timedelta(hours=1),
            "H4": timedelta(hours=4),
            "D1": timedelta(days=1),
        }[timeframe]
        anchor = end_time_utc or datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)
        candles = []
        for index in range(60):
            close = 0.4660 - (index * 0.0001)
            candles.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": anchor - step * (59 - index),
                    "open": close + 0.00005,
                    "high": close + 0.00020,
                    "low": close - 0.00020,
                    "close": close,
                    "volume": 2000 + index,
                    "source": "fake",
                }
            )
        return candles


def test_market_snapshot_builder_exposes_v2_level_fields() -> None:
    builder = MarketSnapshotBuilder(FakeFinnhubClient())
    block = {
        "id": 9,
        "symbol": "USDJPY",
        "start_utc": datetime(2026, 4, 27, 7, 15, tzinfo=timezone.utc),
        "end_utc": datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc),
    }

    snapshot = asyncio.run(builder.build(block))

    assert snapshot["pivot_mid"] is not None
    assert snapshot["range_low"] is not None
    assert snapshot["range_high"] is not None
    assert snapshot["reclaim_level"] == snapshot["pivot_mid"]
    assert snapshot["nearest_supply_zone"] is not None
    assert snapshot["nearest_demand_zone"] is not None
    assert snapshot["h4_structure"] is not None
    assert snapshot["h4_context_type"] is not None


def test_market_snapshot_builder_uses_utc_end_timestamp_for_price_selection() -> None:
    builder = MarketSnapshotBuilder(FakePreciseFinnhubClient())
    block = {
        "id": 12,
        "symbol": "NZDCHF",
        "start_utc": datetime(2026, 4, 23, 9, 42, 3, tzinfo=timezone.utc),
        "end_utc": datetime(2026, 4, 23, 10, 0, 17, tzinfo=timezone.utc),
    }

    snapshot = asyncio.run(builder.build(block))

    assert snapshot["signal_end_utc"] == datetime(2026, 4, 23, 10, 0, 17, tzinfo=timezone.utc)
    assert snapshot["price_at_end"] == 0.46174
    assert snapshot["price_at_start"] == 0.46210