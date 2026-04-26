from __future__ import annotations

from typing import Any


def pip_size(symbol: str) -> float:
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def decimals(symbol: str) -> int:
    return 3 if "JPY" in symbol.upper() else 5


def zone_text(symbol: str, low: float | None, high: float | None) -> str | None:
    if low is None or high is None:
        return None

    digit_count = decimals(symbol)
    return f"{low:.{digit_count}f}-{high:.{digit_count}f}"


def detect_recent_support_resistance(
    candles: list[dict[str, Any]],
    lookback: int = 80,
) -> tuple[float | None, float | None]:
    if not candles:
        return None, None

    recent = candles[-lookback:]
    support = min(float(candle["low"]) for candle in recent)
    resistance = max(float(candle["high"]) for candle in recent)

    return support, resistance


def detect_levels(
    symbol: str,
    price: float | None,
    d1: list[dict[str, Any]],
    h4: list[dict[str, Any]],
    h1: list[dict[str, Any]],
    m15: list[dict[str, Any]],
) -> dict[str, Any]:
    del d1, h4

    if price is None:
        return {
            "near_support": False,
            "near_resistance": False,
            "support": None,
            "resistance": None,
            "support_zone": None,
            "resistance_zone": None,
            "key_level": None,
        }

    pip = pip_size(symbol)

    h1_support, h1_resistance = detect_recent_support_resistance(h1, 80)
    m15_support, m15_resistance = detect_recent_support_resistance(m15, 120)

    supports = [value for value in [h1_support, m15_support] if value is not None]
    resistances = [value for value in [h1_resistance, m15_resistance] if value is not None]

    support = max(supports) if supports else None
    resistance = min(resistances) if resistances else None

    threshold = 8 * pip if "JPY" in symbol.upper() else 6 * pip

    near_support = abs(price - support) <= threshold if support else False
    near_resistance = abs(price - resistance) <= threshold if resistance else False

    support_zone = zone_text(symbol, support - threshold, support + threshold) if support else None
    resistance_zone = zone_text(symbol, resistance - threshold, resistance + threshold) if resistance else None

    key_level = None
    if near_support:
        key_level = support_zone
    elif near_resistance:
        key_level = resistance_zone

    return {
        "near_support": near_support,
        "near_resistance": near_resistance,
        "support": support,
        "resistance": resistance,
        "support_zone": support_zone,
        "resistance_zone": resistance_zone,
        "key_level": key_level,
    }
