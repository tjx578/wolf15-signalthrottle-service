from __future__ import annotations

from typing import Any


def pip_size(symbol: str) -> float:
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def decimals(symbol: str) -> int:
    return 3 if "JPY" in symbol.upper() else 5


def last_close(candles: list[dict[str, Any]]) -> float | None:
    return float(candles[-1]["close"]) if candles else None


def sma(candles: list[dict[str, Any]], period: int) -> float | None:
    if len(candles) < period:
        return None

    values = [float(candle["close"]) for candle in candles[-period:]]
    return sum(values) / len(values)


def format_price(symbol: str, price: float | None, offset_pips: float, side: str) -> str | None:
    if price is None:
        return None

    pip = pip_size(symbol)

    if side == "above":
        value = price + offset_pips * pip
    else:
        value = price - offset_pips * pip

    return f"{value:.{decimals(symbol)}f}"


def format_zone_around_price(symbol: str, price: float | None, pips: float) -> str | None:
    if price is None:
        return None

    pip = pip_size(symbol)
    low = price - pips * pip
    high = price + pips * pip

    return f"{low:.{decimals(symbol)}f}-{high:.{decimals(symbol)}f}"


def classify_d1_bias(d1: list[dict[str, Any]]) -> str:
    close = last_close(d1)
    ma20 = sma(d1, 20)
    ma50 = sma(d1, 50)

    if close is None or ma20 is None or ma50 is None:
        return "UNCLASSIFIED"

    if close > ma20 > ma50:
        return "BULLISH_MACRO_RANGE"

    if close < ma20 < ma50:
        return "BEARISH_MACRO_RANGE"

    return "TRANSITION_RANGE"


def is_bullish_reclaim(candles: list[dict[str, Any]]) -> bool:
    if len(candles) < 25:
        return False

    close = last_close(candles)
    ma20 = sma(candles, 20)
    prev_close = float(candles[-2]["close"])

    if close is None or ma20 is None:
        return False

    return prev_close < ma20 and close > ma20


def is_bearish_pullback(candles: list[dict[str, Any]]) -> bool:
    if len(candles) < 50:
        return False

    close = last_close(candles)
    ma20 = sma(candles, 20)
    ma50 = sma(candles, 50)

    if close is None or ma20 is None or ma50 is None:
        return False

    return close < ma20 and ma20 <= ma50


def is_upper_rejection(candles: list[dict[str, Any]]) -> bool:
    if len(candles) < 3:
        return False

    candle = candles[-1]
    open_ = float(candle["open"])
    high = float(candle["high"])
    low = float(candle["low"])
    close = float(candle["close"])

    candle_range = max(high - low, 1e-9)
    upper_wick = high - max(open_, close)

    return upper_wick / candle_range >= 0.35 and close < open_


def classify_phase(snapshot: dict[str, Any]) -> dict[str, Any]:
    symbol = snapshot["symbol"]
    price = snapshot.get("price")

    d1 = snapshot.get("d1", [])
    h1 = snapshot.get("h1", [])
    m15 = snapshot.get("m15", [])

    near_support = bool(snapshot.get("near_support", False))
    near_resistance = bool(snapshot.get("near_resistance", False))

    d1_bias = classify_d1_bias(d1)
    h1_reclaim = is_bullish_reclaim(h1)
    m15_reclaim = is_bullish_reclaim(m15)
    h1_bearish_pullback = is_bearish_pullback(h1)
    m15_bearish_pullback = is_bearish_pullback(m15)
    m15_rejection = is_upper_rejection(m15)

    if near_resistance and m15_rejection:
        return {
            "d1_bias": d1_bias,
            "h4_structure": "UPPER_RANGE",
            "h1_phase": "RESISTANCE_RETEST",
            "m15_phase": "REJECTION",
            "chart_bias": "RANGE_OR_UPPER_PRESSURE",
            "chart_phase": "UPPER_RANGE_EXHAUSTION_RISK",
            "action": "PROTECT_LONG_OR_SELL_REJECTION",
            "entry_zone": snapshot.get("resistance_zone"),
            "invalidation": format_price(symbol, snapshot.get("resistance"), 15, "above"),
            "tp1": format_price(symbol, price, 20, "below"),
            "tp2": snapshot.get("support_zone"),
            "tp3": format_price(symbol, price, 50, "below"),
        }

    if (h1_reclaim or m15_reclaim) and not near_resistance:
        return {
            "d1_bias": d1_bias,
            "h4_structure": "PIVOT_RECLAIM",
            "h1_phase": "RECLAIM",
            "m15_phase": "RECLAIM_CONTINUATION",
            "chart_bias": d1_bias,
            "chart_phase": "PIVOT_RECLAIM_CONTINUATION",
            "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD",
            "entry_zone": format_zone_around_price(symbol, price, 8),
            "invalidation": format_price(symbol, price, 18, "below"),
            "tp1": format_price(symbol, price, 20, "above"),
            "tp2": format_price(symbol, price, 35, "above"),
            "tp3": snapshot.get("resistance_zone"),
        }

    if (h1_bearish_pullback or m15_bearish_pullback) and not near_support:
        return {
            "d1_bias": d1_bias,
            "h4_structure": "PULLBACK_AFTER_RALLY",
            "h1_phase": "BEARISH_PULLBACK",
            "m15_phase": "PULLBACK_CONTINUATION",
            "chart_bias": "TRANSITION_AFTER_RALLY",
            "chart_phase": "BEARISH_PULLBACK_CONTINUATION",
            "action": "SELL_ON_RALLY_OR_CONTINUATION",
            "entry_zone": format_zone_around_price(symbol, price, 8),
            "invalidation": format_price(symbol, price, 18, "above"),
            "tp1": format_price(symbol, price, 20, "below"),
            "tp2": snapshot.get("support_zone"),
            "tp3": format_price(symbol, price, 50, "below"),
        }

    if near_support:
        return {
            "d1_bias": d1_bias,
            "h4_structure": "SUPPORT_TEST",
            "h1_phase": "SUPPORT_DECISION",
            "m15_phase": "SUPPORT_DECISION",
            "chart_bias": "SUPPORT_TEST",
            "chart_phase": "SUPPORT_DECISION_ZONE",
            "action": "WAIT_BREAKDOWN_OR_RECLAIM",
            "entry_zone": snapshot.get("support_zone"),
            "invalidation": None,
            "tp1": None,
            "tp2": None,
            "tp3": None,
        }

    return {
        "d1_bias": d1_bias,
        "h4_structure": "RANGE",
        "h1_phase": "MID_RANGE",
        "m15_phase": "MID_RANGE",
        "chart_bias": "UNCLASSIFIED",
        "chart_phase": "RANGE_MID_NO_EDGE",
        "action": "NO_TRADE_WAIT_CONTEXT",
        "entry_zone": None,
        "invalidation": None,
        "tp1": None,
        "tp2": None,
        "tp3": None,
    }
