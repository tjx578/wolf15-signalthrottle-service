from __future__ import annotations


def classify_phase(snapshot: dict) -> dict:
    """Classify chart phase from market snapshot data.

    Input snapshot keys:
        price, near_resistance, near_support,
        pivot_reclaim, pullback_active, m15_rejection

    Returns dict with chart_bias, chart_phase, action.
    """
    near_resistance = snapshot.get("near_resistance", False)
    near_support = snapshot.get("near_support", False)
    pivot_reclaim = snapshot.get("pivot_reclaim", False)
    pullback_active = snapshot.get("pullback_active", False)
    m15_rejection = snapshot.get("m15_rejection", False)

    if pivot_reclaim and not near_resistance:
        return {
            "chart_bias": "BULLISH_MACRO_RANGE",
            "chart_phase": "PIVOT_RECLAIM_CONTINUATION",
            "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD",
        }

    if near_resistance and m15_rejection:
        return {
            "chart_bias": "RANGE_OR_UPPER_PRESSURE",
            "chart_phase": "UPPER_RANGE_EXHAUSTION_RISK",
            "action": "PROTECT_LONG_OR_SELL_REJECTION",
        }

    if pullback_active and not near_support:
        return {
            "chart_bias": "TRANSITION_AFTER_RALLY",
            "chart_phase": "BEARISH_PULLBACK_CONTINUATION",
            "action": "SELL_ON_RALLY_OR_CONTINUATION",
        }

    if near_support:
        return {
            "chart_bias": "SUPPORT_TEST",
            "chart_phase": "SUPPORT_DECISION_ZONE",
            "action": "WAIT_BREAKDOWN_OR_RECLAIM",
        }

    return {
        "chart_bias": "UNCLASSIFIED",
        "chart_phase": "RANGE_MID_NO_EDGE",
        "action": "NO_TRADE_WAIT_CONTEXT",
    }
