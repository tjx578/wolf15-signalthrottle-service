from __future__ import annotations

import logging

from app.config import settings
from app.market.finnhub_client import FinnhubClient
from app.market.level_detector import detect_levels
from app.market.ohlc_cache import ohlc_cache
from app.market.phase_classifier import classify_phase

logger = logging.getLogger(__name__)


async def build_market_snapshot(symbol: str) -> dict:
    """Fetch OHLC, detect levels, classify phase, return snapshot dict."""

    if not settings.finnhub_api_key:
        return _empty_snapshot(symbol)

    client = FinnhubClient(api_key=settings.finnhub_api_key)

    # Fetch with cache
    m15 = ohlc_cache.get(symbol, "M15")
    if m15 is None:
        try:
            m15 = await client.fetch(symbol, "M15", bars=50)
            ohlc_cache.put(symbol, "M15", m15)
        except Exception as exc:
            logger.warning("M15 fetch failed for %s: %s", symbol, exc)
            m15 = []

    h1 = ohlc_cache.get(symbol, "H1")
    if h1 is None:
        try:
            h1 = await client.fetch(symbol, "H1", bars=50)
            ohlc_cache.put(symbol, "H1", h1)
        except Exception as exc:
            logger.warning("H1 fetch failed for %s: %s", symbol, exc)
            h1 = []

    # Detect levels from H1
    levels = detect_levels(h1, lookback=20)
    last_price = m15[-1]["close"] if m15 else (h1[-1]["close"] if h1 else None)

    # Build snapshot for phase classifier
    snapshot_input = {
        "price": last_price,
        "near_resistance": levels.get("near_resistance", False),
        "near_support": levels.get("near_support", False),
        "pivot_reclaim": False,  # TODO: detect from structure
        "pullback_active": False,  # TODO: detect from structure
        "m15_rejection": False,  # TODO: detect from M15 patterns
    }

    phase = classify_phase(snapshot_input)

    return {
        "symbol": symbol,
        "price_at_end": last_price,
        "support_zone": str(levels.get("support")) if levels.get("support") else None,
        "resistance_zone": str(levels.get("resistance")) if levels.get("resistance") else None,
        "chart_bias": phase["chart_bias"],
        "chart_phase": phase["chart_phase"],
        "action": phase["action"],
        "near_support": levels.get("near_support", False),
        "near_resistance": levels.get("near_resistance", False),
        "m15_bars": len(m15),
        "h1_bars": len(h1),
    }


def _empty_snapshot(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "price_at_end": None,
        "support_zone": None,
        "resistance_zone": None,
        "chart_bias": "UNCLASSIFIED",
        "chart_phase": "NO_DATA",
        "action": "NO_TRADE_WAIT_CONTEXT",
        "near_support": False,
        "near_resistance": False,
        "m15_bars": 0,
        "h1_bars": 0,
    }
