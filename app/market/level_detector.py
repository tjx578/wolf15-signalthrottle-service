from __future__ import annotations


def detect_levels(candles: list[dict], lookback: int = 20) -> dict:
    """Simple support/resistance detection from recent candles.

    Returns dict with support, resistance, and distance info.
    """
    if not candles or len(candles) < 5:
        return {
            "support": None,
            "resistance": None,
            "near_support": False,
            "near_resistance": False,
        }

    recent = candles[-lookback:]
    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]
    last_close = recent[-1]["close"]

    resistance = max(highs)
    support = min(lows)
    price_range = resistance - support

    if price_range == 0:
        return {
            "support": support,
            "resistance": resistance,
            "near_support": False,
            "near_resistance": False,
        }

    # "Near" = within 15% of range from level
    threshold = price_range * 0.15
    near_resistance = (resistance - last_close) <= threshold
    near_support = (last_close - support) <= threshold

    return {
        "support": round(support, 5),
        "resistance": round(resistance, 5),
        "near_support": near_support,
        "near_resistance": near_resistance,
        "price_range": round(price_range, 5),
    }
