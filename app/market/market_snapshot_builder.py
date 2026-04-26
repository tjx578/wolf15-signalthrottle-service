from __future__ import annotations

from datetime import datetime
from typing import Any

from app.market.finnhub_client import FinnhubClient
from app.market.level_detector import detect_levels
from app.market.phase_classifier import classify_phase


def find_candle_at_or_before(
    candles: list[dict[str, Any]],
    ts: datetime,
) -> dict[str, Any] | None:
    valid = [candle for candle in candles if candle["timestamp"] <= ts]
    if not valid:
        return None

    return sorted(valid, key=lambda candle: candle["timestamp"])[-1]


class MarketSnapshotBuilder:
    def __init__(self, ohlc_client: FinnhubClient) -> None:
        self.ohlc_client = ohlc_client

    async def build(self, block: dict[str, Any]) -> dict[str, Any]:
        symbol = block["symbol"]
        start_utc = block["start_utc"]
        end_utc = block["end_utc"]

        m15 = await self.ohlc_client.fetch(symbol, "M15", bars=250, end_time_utc=end_utc)
        h1 = await self.ohlc_client.fetch(symbol, "H1", bars=200, end_time_utc=end_utc)
        h4 = await self.ohlc_client.fetch(symbol, "H4", bars=120, end_time_utc=end_utc)
        d1 = await self.ohlc_client.fetch(symbol, "D1", bars=120, end_time_utc=end_utc)

        m15_end = find_candle_at_or_before(m15, end_utc)
        m15_start = find_candle_at_or_before(m15, start_utc)

        price_at_end = float(m15_end["close"]) if m15_end else None
        price_at_start = float(m15_start["close"]) if m15_start else None

        level_context = detect_levels(
            symbol=symbol,
            price=price_at_end,
            d1=d1,
            h4=h4,
            h1=h1,
            m15=m15,
        )

        phase = classify_phase(
            {
                "symbol": symbol,
                "price": price_at_end,
                "d1": d1,
                "h4": h4,
                "h1": h1,
                "m15": m15,
                **level_context,
            }
        )

        return {
            "symbol": symbol,
            "block_id": block.get("id"),
            "signal_start_utc": start_utc,
            "signal_end_utc": end_utc,
            "price_at_start": price_at_start,
            "price_at_end": price_at_end,
            **level_context,
            **phase,
            "raw_ohlc": {
                "D1": d1[-50:],
                "H4": h4[-80:],
                "H1": h1[-100:],
                "M15": m15[-120:],
            },
        }
