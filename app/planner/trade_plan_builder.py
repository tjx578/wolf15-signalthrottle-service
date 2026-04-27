from __future__ import annotations

from typing import Any


STRONG_PHASES = {
    "PIVOT_RECLAIM_CONTINUATION",
    "HIGH_BASE_COMPRESSION",
    "PULLBACK_TO_SUPPORT",
    "BREAKOUT_RETEST",
    "BEARISH_PULLBACK_CONTINUATION",
    "UPPER_RANGE_EXHAUSTION_RISK",
    "FAILED_RECLAIM",
    "BREAKDOWN_CONFIRMATION",
}

DECISION_PHASES = {
    "SUPPORT_DECISION_ZONE",
    "SUPPORT_REACTION_PENDING",
    "RESISTANCE_DECISION_ZONE",
    "UPPER_RANGE_DISTRIBUTION",
}

WAIT_ACTIONS = {
    "NO_TRADE",
    "NO_TRADE_WAIT_CONTEXT",
    "WAIT",
}

GRADE_DOWNGRADE = {
    "A": "B+",
    "B+": "B",
    "B": "C",
    "C": "C",
}


def _is_wait_action(action: str) -> bool:
    """An action counts as 'wait' if it is in WAIT_ACTIONS or starts with the
    WAIT_ prefix used by the action_mapper for context-pending phases
    (e.g. WAIT_SUPPORT_REACTION_OR_RECLAIM, WAIT_BREAKDOWN_OR_RECLAIM)."""
    if not action:
        return True
    if action in WAIT_ACTIONS:
        return True
    return action.startswith("WAIT_") or action.startswith("NO_TRADE")


def _apply_h4_context_to_grade(base_grade: str, h4_context_type: str | None) -> str:
    # Range-edge compression is a weaker exhaustion subtype than failed
    # breakout/breakdown acceptance or terminal rejection, so it gets a one-step
    # downgrade in execution quality.
    if h4_context_type == "RANGE_EDGE_COMPRESSION":
        return GRADE_DOWNGRADE.get(base_grade, base_grade)
    return base_grade


def grade_execution(
    pressure_grade: str,
    chart_phase: str,
    h4_context_type: str | None = None,
) -> str:
    if chart_phase in STRONG_PHASES:
        if pressure_grade in {"A+", "A", "A-"}:
            return _apply_h4_context_to_grade("A", h4_context_type)
        if pressure_grade == "B+":
            return _apply_h4_context_to_grade("B+", h4_context_type)

    if chart_phase in DECISION_PHASES:
        if pressure_grade in {"A+", "A", "A-"}:
            return _apply_h4_context_to_grade("B+", h4_context_type)
        if pressure_grade == "B+":
            return _apply_h4_context_to_grade("B", h4_context_type)

    if chart_phase == "RANGE_MID_NO_EDGE":
        return "C"

    return _apply_h4_context_to_grade("B", h4_context_type)


def map_execution_side(chart_phase: str) -> str:
    mapping = {
        "PIVOT_RECLAIM_CONTINUATION": "BUY_CONTINUATION",
        "HIGH_BASE_COMPRESSION": "BUY_BREAKOUT_OR_RETEST",
        "PULLBACK_TO_SUPPORT": "WAIT_SUPPORT_REACTION_OR_RECLAIM",
        "BREAKOUT_RETEST": "BUY_BREAKOUT_RETEST",
        "UPPER_RANGE_EXHAUSTION_RISK": "PROTECT_LONG_OR_SELL_REJECTION",
        "UPPER_RANGE_DISTRIBUTION": "WAIT_BREAKOUT_OR_REJECTION",
        "BEARISH_PULLBACK_CONTINUATION": "SELL_ON_RALLY_OR_CONTINUATION",
        "FAILED_RECLAIM": "SELL_FAILED_RECLAIM",
        "BREAKDOWN_CONFIRMATION": "SELL_BREAKDOWN_RETEST",
        "SUPPORT_DECISION_ZONE": "WAIT_BREAKDOWN_OR_RECLAIM",
        "SUPPORT_REACTION_PENDING": "WAIT_SUPPORT_REACTION_OR_RECLAIM",
        "RESISTANCE_DECISION_ZONE": "WAIT_BREAKOUT_OR_REJECTION",
        "RANGE_MID_NO_EDGE": "NO_TRADE",
    }
    return mapping.get(chart_phase, "WAIT")


def pressure_status_from_grade(pressure_grade: str) -> str:
    if pressure_grade == "A+":
        return "PRIORITY_PRESSURE"
    if pressure_grade in {"A", "A-"}:
        return "VALID_PRESSURE"
    if pressure_grade == "B+":
        return "WATCHLIST_PRESSURE"
    return "LOW_QUALITY_PRESSURE"


def is_actionable_signal(execution_grade: str, action: str) -> bool:
    return execution_grade in {"B+", "A", "A+"} and not _is_wait_action(action)


def build_message(
    block: dict[str, Any],
    snapshot: dict[str, Any],
    execution_grade: str,
    execution_side: str,
) -> str:
    symbol = block["symbol"]
    pressure_grade = block["pressure_grade"]
    phase = snapshot["chart_phase"]
    action = snapshot["action"]
    zone = snapshot.get("entry_zone") or "n/a"
    reason_code = snapshot.get("reason_code") or "UNCLASSIFIED"

    return (
        f"{symbol} {pressure_grade} pressure. "
        f"Execution {execution_grade}. "
        f"Phase: {phase}. "
        f"Action: {action}. "
        f"Reason: {reason_code}. "
        f"Zone: {zone}. "
        f"Side: {execution_side}."
    )


def build_trade_plan(block: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    pressure_grade = block["pressure_grade"]
    chart_phase = snapshot["chart_phase"]
    action = snapshot["action"]
    h4_context_type = snapshot.get("h4_context_type")

    execution_grade = grade_execution(pressure_grade, chart_phase, h4_context_type)
    execution_side = map_execution_side(chart_phase)

    # Canonical rule: any B+/A-/A/A+ block that has reached this point HAS a
    # trade plan, therefore it belongs in the "ready" bucket on the dashboard.
    # The previous behavior of demoting B+/A- to "watchlist" hid valid plans.
    valid_grades = {"B+", "A-", "A", "A+"}
    is_valid_pressure = pressure_grade in valid_grades
    has_trade_context = not _is_wait_action(action)
    if is_valid_pressure and has_trade_context:
        signal_bucket = "ready"
    elif is_valid_pressure:
        # Plan exists but no actionable edge yet — still a watchlist row, the
        # dashboard will surface the WAIT action and reason.
        signal_bucket = "watchlist"
    else:
        signal_bucket = "watchlist"

    # Owner-alert eligibility (e.g. Telegram push) stays stricter: only A/A+
    # with an actionable execution should ping the owner. B+ and A- continue
    # to live in the dashboard but should not generate noisy alerts.
    owner_alert = (
        pressure_grade in {"A", "A+"}
        and is_actionable_signal(execution_grade, action)
    )

    price_at_end = snapshot.get("price_at_end")
    price_text = None
    if price_at_end is not None:
        digit_count = 3 if "JPY" in block["symbol"] else 5
        price_text = f"{float(price_at_end):.{digit_count}f}"

    scenario_set = {
        "primary_scenario": snapshot.get("primary_scenario"),
        "alternative_scenario": snapshot.get("alternative_scenario"),
        "no_trade_condition": snapshot.get("no_trade_condition"),
    }
    reason_code = snapshot.get("reason_code") or "UNCLASSIFIED"

    return {
        "symbol": block["symbol"],
        "signal_type": "SIGNAL_THROTTLE_PRESSURE",
        "pressure_status": pressure_status_from_grade(pressure_grade),
        "signal_bucket": signal_bucket,
        "owner_alert": owner_alert,
        "pressure_grade": pressure_grade,
        "execution_grade": execution_grade,
        "execution_side": execution_side,
        "signal_start_utc": block.get("start_utc"),
        "signal_end_utc": block.get("end_utc"),
        "signal_start_wita": block.get("start_wita"),
        "signal_end_wita": block.get("end_wita"),
        "chart_time_start": block.get("chart_start_time"),
        "chart_time_end": block.get("chart_end_time"),
        "duration_minutes": block.get("duration_minutes"),
        "event_count": block.get("event_count"),
        "density_per_minute": block.get("density_per_minute"),
        "max_gap_seconds": block.get("max_gap_seconds"),
        "avg_gap_seconds": block.get("avg_gap_seconds"),
        "block_relation": block.get("block_relation", "UNKNOWN"),
        "finalize_mode": block.get("finalize_mode", "SOFT_FINALIZED"),
        "price_at_signal_end": price_text,
        "chart_bias": snapshot["chart_bias"],
        "chart_phase": chart_phase,
        "h4_context_type": h4_context_type,
        "action": action,
        "reason_code": reason_code,
        "entry_zone": snapshot.get("entry_zone"),
        "breakout_level": snapshot.get("breakout_level"),
        "reclaim_level": snapshot.get("reclaim_level"),
        "invalidation": snapshot.get("invalidation"),
        "tp1": snapshot.get("tp1"),
        "tp2": snapshot.get("tp2"),
        "tp3": snapshot.get("tp3"),
        "message": build_message(block, snapshot, execution_grade, execution_side),
        "payload": {
            "block": block,
            "snapshot": {
                key: value
                for key, value in snapshot.items()
                if key != "raw_ohlc"
            },
            "scenario_set": scenario_set,
        },
    }
