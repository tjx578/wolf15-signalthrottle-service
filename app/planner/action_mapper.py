from __future__ import annotations


def map_action(chart_phase: str, pressure_grade: str) -> str:
    """Map chart phase + pressure grade to recommended action string."""
    actions = {
        "PIVOT_RECLAIM_CONTINUATION": "BUY_ON_RETEST_OR_RECLAIM_HOLD",
        "UPPER_RANGE_EXHAUSTION_RISK": "PROTECT_LONG_OR_SELL_REJECTION",
        "BEARISH_PULLBACK_CONTINUATION": "SELL_ON_RALLY_OR_CONTINUATION",
        "SUPPORT_DECISION_ZONE": "WAIT_BREAKDOWN_OR_RECLAIM",
        "RANGE_MID_NO_EDGE": "NO_TRADE_WAIT_CONTEXT",
    }
    return actions.get(chart_phase, "NO_TRADE_WAIT_CONTEXT")
