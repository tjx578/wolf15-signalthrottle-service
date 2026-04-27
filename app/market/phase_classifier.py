from __future__ import annotations

from typing import Any


def _scenario(
    *,
    label: str,
    action: str,
    trigger: str,
    entry_zone: str | None = None,
    invalidation: str | None = None,
    tp1: str | None = None,
    tp2: str | None = None,
    tp3: str | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "action": action,
        "trigger": trigger,
        "entry_zone": entry_zone,
        "invalidation": invalidation,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
    }


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


def is_breakdown_confirmation(snapshot: dict[str, Any]) -> bool:
    price = snapshot.get("price")
    support = snapshot.get("support")
    m15 = snapshot.get("m15", [])
    if price is None or support is None or len(m15) < 2:
        return False

    close = float(m15[-1]["close"])
    prev_close = float(m15[-2]["close"])
    return prev_close >= support and close < support


def is_failed_reclaim(snapshot: dict[str, Any]) -> bool:
    price = snapshot.get("price")
    reclaim_level = snapshot.get("reclaim_level")
    m15 = snapshot.get("m15", [])
    if price is None or reclaim_level is None or len(m15) < 3:
        return False

    close = float(m15[-1]["close"])
    prev_close = float(m15[-2]["close"])
    return prev_close >= reclaim_level and close < reclaim_level


def is_high_base_compression(snapshot: dict[str, Any]) -> bool:
    m15 = snapshot.get("m15", [])
    if snapshot.get("near_support") or snapshot.get("near_resistance"):
        return False
    if len(m15) < 8:
        return False

    recent = m15[-8:]
    highs = [float(candle["high"]) for candle in recent]
    lows = [float(candle["low"]) for candle in recent]
    closes = [float(candle["close"]) for candle in recent]
    total_range = max(highs) - min(lows)
    if total_range <= 0:
        return False

    close_position = (closes[-1] - min(lows)) / total_range
    return (
        total_range <= max(closes[-1] * 0.0025, 0.05)
        and close_position >= 0.65
        and not is_bullish_reclaim(m15)
    )


def _base_phase_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "d1_bias": classify_d1_bias(snapshot.get("d1", [])),
        "primary_scenario": None,
        "alternative_scenario": None,
        "no_trade_condition": None,
        "reason_code": "UNCLASSIFIED",
    }


def _phase_result(snapshot: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    result = _base_phase_payload(snapshot)
    result.update(overrides)
    return result


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

    support_zone = snapshot.get("support_zone")
    resistance_zone = snapshot.get("resistance_zone")
    support = snapshot.get("support")
    resistance = snapshot.get("resistance")
    reclaim_level = snapshot.get("reclaim_level") or snapshot.get("pivot_mid")
    breakdown_level = snapshot.get("breakdown_level") or support
    breakout_level = snapshot.get("breakout_level") or resistance

    if near_resistance and m15_rejection:
        return _phase_result(
            snapshot,
            d1_bias=d1_bias,
            h4_structure="UPPER_RANGE",
            h1_phase="RESISTANCE_RETEST",
            m15_phase="REJECTION",
            chart_bias="RANGE_OR_UPPER_PRESSURE",
            chart_phase="UPPER_RANGE_EXHAUSTION_RISK",
            action="PROTECT_LONG_OR_SELL_REJECTION",
            entry_zone=resistance_zone,
            reclaim_level=reclaim_level,
            breakout_level=breakout_level,
            invalidation=format_price(symbol, resistance, 15, "above"),
            tp1=format_price(symbol, price, 20, "below"),
            tp2=support_zone,
            tp3=format_price(symbol, price, 50, "below"),
            reason_code="UPPER_RESISTANCE_REJECTION",
            primary_scenario=_scenario(
                label="primary",
                action="SELL_REJECTION",
                trigger="M15 rejection confirmed at upper resistance zone",
                entry_zone=resistance_zone,
                invalidation=format_price(symbol, resistance, 15, "above"),
                tp1=format_price(symbol, price, 20, "below"),
                tp2=support_zone,
                tp3=format_price(symbol, price, 50, "below"),
            ),
            alternative_scenario=_scenario(
                label="alternative",
                action="BUY_BREAKOUT_RETEST",
                trigger="Breakout acceptance above resistance then retest holds",
                entry_zone=resistance_zone,
                invalidation=format_price(symbol, resistance, 10, "below"),
                tp1=format_price(symbol, price, 20, "above"),
                tp2=format_price(symbol, price, 35, "above"),
                tp3=format_price(symbol, price, 50, "above"),
            ),
            no_trade_condition="No edge while price stays pinned below resistance without rejection confirmation.",
        )

    if near_resistance:
        return _phase_result(
            snapshot,
            d1_bias=d1_bias,
            h4_structure="UPPER_RANGE",
            h1_phase="RESISTANCE_RETEST",
            m15_phase="DISTRIBUTION",
            chart_bias="RANGE_OR_UPPER_PRESSURE",
            chart_phase="UPPER_RANGE_DISTRIBUTION",
            action="WAIT_BREAKOUT_OR_REJECTION",
            entry_zone=resistance_zone,
            reclaim_level=reclaim_level,
            breakout_level=breakout_level,
            invalidation=format_price(symbol, resistance, 15, "above"),
            tp1=None,
            tp2=None,
            tp3=None,
            reason_code="UPPER_RANGE_DISTRIBUTION",
            primary_scenario=_scenario(
                label="primary",
                action="WAIT_BREAKOUT_OR_REJECTION",
                trigger="Wait for either breakout acceptance above resistance or rejection wick confirmation",
                entry_zone=resistance_zone,
                invalidation=format_price(symbol, resistance, 15, "above"),
            ),
            alternative_scenario=_scenario(
                label="alternative",
                action="PROTECT_LONG_OR_SELL_REJECTION",
                trigger="If rejection confirms, pivot to sell rejection setup",
                entry_zone=resistance_zone,
                invalidation=format_price(symbol, resistance, 15, "above"),
                tp1=format_price(symbol, price, 20, "below"),
                tp2=support_zone,
                tp3=format_price(symbol, price, 50, "below"),
            ),
            no_trade_condition="Do not chase longs inside upper-range distribution without breakout acceptance.",
        )

    if is_failed_reclaim(snapshot):
        return _phase_result(
            snapshot,
            d1_bias=d1_bias,
            h4_structure="FAILED_RECLAIM",
            h1_phase="FAILED_RECLAIM",
            m15_phase="FAILED_RECLAIM",
            chart_bias="TRANSITION_AFTER_FAILED_RECLAIM",
            chart_phase="FAILED_RECLAIM",
            action="SELL_ON_RALLY_OR_CONTINUATION",
            entry_zone=format_zone_around_price(symbol, reclaim_level, 6),
            reclaim_level=format_price(symbol, reclaim_level, 0, "above") if reclaim_level is not None else None,
            breakdown_level=breakdown_level,
            invalidation=format_price(symbol, reclaim_level, 15, "above"),
            tp1=support_zone,
            tp2=format_price(symbol, price, 35, "below"),
            tp3=format_price(symbol, price, 50, "below"),
            reason_code="FAILED_RECLAIM_AT_PIVOT",
            primary_scenario=_scenario(
                label="primary",
                action="SELL_FAILED_RECLAIM",
                trigger="Price failed to hold above reclaim level and rolled back under pivot",
                entry_zone=format_zone_around_price(symbol, reclaim_level, 6),
                invalidation=format_price(symbol, reclaim_level, 15, "above"),
                tp1=support_zone,
                tp2=format_price(symbol, price, 35, "below"),
                tp3=format_price(symbol, price, 50, "below"),
            ),
            alternative_scenario=_scenario(
                label="alternative",
                action="WAIT_SUPPORT_REACTION_OR_RECLAIM",
                trigger="If support reacts cleanly, wait for reclaim back above pivot",
                entry_zone=support_zone,
                invalidation=format_price(symbol, support, 12, "below"),
                tp1=format_price(symbol, reclaim_level, 0, "above") if reclaim_level is not None else None,
                tp2=format_price(symbol, price, 20, "above"),
                tp3=resistance_zone,
            ),
            no_trade_condition="No trade if price remains trapped between pivot and support without clear failure or reclaim.",
        )

    if (h1_reclaim or m15_reclaim) and not near_resistance:
        return _phase_result(
            snapshot,
            d1_bias=d1_bias,
            h4_structure="PIVOT_RECLAIM",
            h1_phase="RECLAIM",
            m15_phase="RECLAIM_CONTINUATION",
            chart_bias=d1_bias,
            chart_phase="PIVOT_RECLAIM_CONTINUATION",
            action="BUY_ON_RETEST_OR_RECLAIM_HOLD",
            entry_zone=format_zone_around_price(symbol, price, 8),
            reclaim_level=reclaim_level,
            breakout_level=breakout_level,
            invalidation=format_price(symbol, price, 18, "below"),
            tp1=format_price(symbol, price, 20, "above"),
            tp2=format_price(symbol, price, 35, "above"),
            tp3=resistance_zone,
            reason_code="PIVOT_RECLAIM_VALID",
            primary_scenario=_scenario(
                label="primary",
                action="BUY_ON_RETEST_OR_RECLAIM_HOLD",
                trigger="Reclaim is active and continuation holds above pivot",
                entry_zone=format_zone_around_price(symbol, price, 8),
                invalidation=format_price(symbol, price, 18, "below"),
                tp1=format_price(symbol, price, 20, "above"),
                tp2=format_price(symbol, price, 35, "above"),
                tp3=resistance_zone,
            ),
            alternative_scenario=_scenario(
                label="alternative",
                action="WAIT_SUPPORT_REACTION_OR_RECLAIM",
                trigger="If continuation pauses, wait for support reaction before adding",
                entry_zone=support_zone,
                invalidation=format_price(symbol, support, 12, "below"),
                tp1=format_price(symbol, price, 20, "above"),
            ),
            no_trade_condition="Avoid entry if reclaim loses pivot and slips back into range mid.",
        )

    if is_high_base_compression(snapshot) and not near_resistance:
        return _phase_result(
            snapshot,
            d1_bias=d1_bias,
            h4_structure="HIGH_BASE_COMPRESSION",
            h1_phase="COMPRESSION",
            m15_phase="COMPRESSION",
            chart_bias=d1_bias,
            chart_phase="HIGH_BASE_COMPRESSION",
            action="BUY_BREAKOUT_OR_RETEST",
            entry_zone=format_zone_around_price(symbol, price, 6),
            breakout_level=breakout_level,
            reclaim_level=reclaim_level,
            invalidation=format_price(symbol, price, 15, "below"),
            tp1=format_price(symbol, price, 20, "above"),
            tp2=format_price(symbol, price, 35, "above"),
            tp3=resistance_zone,
            reason_code="HIGH_BASE_COMPRESSION_READY",
            primary_scenario=_scenario(
                label="primary",
                action="BUY_BREAKOUT_OR_RETEST",
                trigger="Compression resolves upward and breakout level holds on retest",
                entry_zone=format_zone_around_price(symbol, price, 6),
                invalidation=format_price(symbol, price, 15, "below"),
                tp1=format_price(symbol, price, 20, "above"),
                tp2=format_price(symbol, price, 35, "above"),
                tp3=resistance_zone,
            ),
            alternative_scenario=_scenario(
                label="alternative",
                action="WAIT_BREAKDOWN_OR_RECLAIM",
                trigger="If compression breaks down, wait for support reaction before re-entry",
                entry_zone=support_zone,
                invalidation=format_price(symbol, support, 12, "below"),
            ),
            no_trade_condition="No trade if breakout has not yet resolved the compression range.",
        )

    if is_breakdown_confirmation(snapshot):
        return _phase_result(
            snapshot,
            d1_bias=d1_bias,
            h4_structure="BREAKDOWN",
            h1_phase="BREAKDOWN",
            m15_phase="BREAKDOWN_CONFIRMATION",
            chart_bias="BEARISH_BREAKDOWN",
            chart_phase="BREAKDOWN_CONFIRMATION",
            action="SELL_ON_RALLY_OR_CONTINUATION",
            entry_zone=format_zone_around_price(symbol, breakdown_level, 6),
            breakdown_level=breakdown_level,
            invalidation=format_price(symbol, breakdown_level, 15, "above"),
            tp1=format_price(symbol, price, 20, "below"),
            tp2=support_zone,
            tp3=format_price(symbol, price, 50, "below"),
            reason_code="SUPPORT_BREAKDOWN_CONFIRMED",
            primary_scenario=_scenario(
                label="primary",
                action="SELL_BREAKDOWN_RETEST",
                trigger="Support has broken and retest fails beneath breakdown level",
                entry_zone=format_zone_around_price(symbol, breakdown_level, 6),
                invalidation=format_price(symbol, breakdown_level, 15, "above"),
                tp1=format_price(symbol, price, 20, "below"),
                tp2=support_zone,
                tp3=format_price(symbol, price, 50, "below"),
            ),
            alternative_scenario=_scenario(
                label="alternative",
                action="WAIT_BREAKDOWN_OR_RECLAIM",
                trigger="If breakdown fails, wait for reclaim back above support before acting",
                entry_zone=support_zone,
                invalidation=format_price(symbol, support, 12, "below"),
            ),
            no_trade_condition="No trade while the breakdown has not yet confirmed with a close below support.",
        )

    if (h1_bearish_pullback or m15_bearish_pullback) and not near_support:
        return _phase_result(
            snapshot,
            d1_bias=d1_bias,
            h4_structure="PULLBACK_AFTER_RALLY",
            h1_phase="BEARISH_PULLBACK",
            m15_phase="PULLBACK_CONTINUATION",
            chart_bias="TRANSITION_AFTER_RALLY",
            chart_phase="BEARISH_PULLBACK_CONTINUATION",
            action="SELL_ON_RALLY_OR_CONTINUATION",
            entry_zone=format_zone_around_price(symbol, price, 8),
            reclaim_level=reclaim_level,
            breakdown_level=breakdown_level,
            invalidation=format_price(symbol, price, 18, "above"),
            tp1=format_price(symbol, price, 20, "below"),
            tp2=support_zone,
            tp3=format_price(symbol, price, 50, "below"),
            reason_code="LOWER_HIGH_REJECTION",
            primary_scenario=_scenario(
                label="primary",
                action="SELL_ON_RALLY_OR_CONTINUATION",
                trigger="H1/M15 bearish pullback is active and lower-high rejection remains intact",
                entry_zone=format_zone_around_price(symbol, price, 8),
                invalidation=format_price(symbol, price, 18, "above"),
                tp1=format_price(symbol, price, 20, "below"),
                tp2=support_zone,
                tp3=format_price(symbol, price, 50, "below"),
            ),
            alternative_scenario=_scenario(
                label="alternative",
                action="WAIT_BREAKDOWN_OR_RECLAIM",
                trigger="If price stabilizes near support, wait for clearer reclaim/breakdown signal",
                entry_zone=support_zone,
            ),
            no_trade_condition="No trade in mid-range pullback without lower-high confirmation.",
        )

    if near_support:
        return _phase_result(
            snapshot,
            d1_bias=d1_bias,
            h4_structure="SUPPORT_TEST",
            h1_phase="SUPPORT_DECISION",
            m15_phase="SUPPORT_DECISION",
            chart_bias="SUPPORT_TEST",
            chart_phase="SUPPORT_REACTION_PENDING",
            action="WAIT_SUPPORT_REACTION_OR_RECLAIM",
            entry_zone=support_zone,
            reclaim_level=reclaim_level,
            breakdown_level=breakdown_level,
            invalidation=None,
            tp1=None,
            tp2=None,
            tp3=None,
            reason_code="SUPPORT_DECISION_PENDING",
            primary_scenario=_scenario(
                label="primary",
                action="WAIT_SUPPORT_REACTION_OR_RECLAIM",
                trigger="Wait for bullish reaction or reclaim from support decision zone",
                entry_zone=support_zone,
            ),
            alternative_scenario=_scenario(
                label="alternative",
                action="SELL_BREAKDOWN_RETEST",
                trigger="If support breaks and retest fails, switch to breakdown continuation",
                entry_zone=format_zone_around_price(symbol, breakdown_level, 6),
            ),
            no_trade_condition="No trade while price is sitting in support without confirmation.",
        )

    return _phase_result(
        snapshot,
        d1_bias=d1_bias,
        h4_structure="RANGE",
        h1_phase="MID_RANGE",
        m15_phase="MID_RANGE",
        chart_bias="UNCLASSIFIED",
        chart_phase="RANGE_MID_NO_EDGE",
        action="NO_TRADE_WAIT_CONTEXT",
        entry_zone=None,
        reclaim_level=reclaim_level,
        breakout_level=breakout_level,
        invalidation=None,
        tp1=None,
        tp2=None,
        tp3=None,
        reason_code="RANGE_MID_NO_EDGE",
        primary_scenario=_scenario(
            label="primary",
            action="NO_TRADE_WAIT_CONTEXT",
            trigger="Price is mid-range without reclaim, breakdown, or rejection edge",
        ),
        alternative_scenario=None,
        no_trade_condition="No trade until price reaches a decision zone or confirms a structural reclaim/breakdown.",
    )
