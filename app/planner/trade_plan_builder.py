from __future__ import annotations


def build_trade_plan(block: dict, snapshot: dict, phase: dict) -> dict:
    pressure_grade = block["pressure_grade"]
    chart_phase = phase.get("chart_phase", "UNCLASSIFIED")
    action = phase.get("action", "NO_TRADE_WAIT_CONTEXT")

    execution_grade = "B"
    execution_side = "WAIT"

    if pressure_grade in {"A", "A+"} and chart_phase in {
        "PIVOT_RECLAIM_CONTINUATION",
        "UPPER_RANGE_EXHAUSTION_RISK",
        "BEARISH_PULLBACK_CONTINUATION",
    }:
        execution_grade = "A"

    if chart_phase == "PIVOT_RECLAIM_CONTINUATION":
        execution_side = "BUY_CONTINUATION"
    elif chart_phase == "UPPER_RANGE_EXHAUSTION_RISK":
        execution_side = "PROTECT_LONG_OR_SELL_REJECTION"
    elif chart_phase == "BEARISH_PULLBACK_CONTINUATION":
        execution_side = "SELL_ON_RALLY_OR_CONTINUATION"
    elif chart_phase == "SUPPORT_DECISION_ZONE":
        execution_side = "WAIT_BREAKDOWN_OR_RECLAIM"

    return {
        "symbol": block["symbol"],
        "signal_type": "SIGNAL_THROTTLE_PRESSURE",
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
        "block_relation": block.get("block_relation"),
        "finalize_mode": block.get("finalize_mode"),
        "price_at_signal_end": snapshot.get("price_at_end"),
        "chart_bias": phase.get("chart_bias"),
        "chart_phase": chart_phase,
        "action": action,
        "entry_zone": snapshot.get("entry_zone"),
        "invalidation": snapshot.get("invalidation"),
        "tp1": snapshot.get("tp1"),
        "tp2": snapshot.get("tp2"),
        "tp3": snapshot.get("tp3"),
        "message": build_message(block, phase, snapshot),
    }


def build_message(block: dict, phase: dict, snapshot: dict) -> str:
    return (
        f"{block['symbol']} {block['pressure_grade']} pressure. "
        f"Phase: {phase.get('chart_phase', 'n/a')}. "
        f"Action: {phase.get('action', 'n/a')}. "
        f"Zone: {snapshot.get('entry_zone', 'n/a')}."
    )
