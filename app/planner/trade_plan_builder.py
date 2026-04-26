from __future__ import annotations

from typing import Any


def grade_execution(pressure_grade: str, chart_phase: str) -> str:
    if pressure_grade in {"A+", "A"} and chart_phase in {
        "PIVOT_RECLAIM_CONTINUATION",
        "UPPER_RANGE_EXHAUSTION_RISK",
        "BEARISH_PULLBACK_CONTINUATION",
    }:
        return "A"

    if pressure_grade in {"A+", "A", "A-"} and chart_phase == "SUPPORT_DECISION_ZONE":
        return "B+"

    if chart_phase == "RANGE_MID_NO_EDGE":
        return "C"

    return "B"


def map_execution_side(chart_phase: str) -> str:
    mapping = {
        "PIVOT_RECLAIM_CONTINUATION": "BUY_CONTINUATION",
        "UPPER_RANGE_EXHAUSTION_RISK": "PROTECT_LONG_OR_SELL_REJECTION",
        "BEARISH_PULLBACK_CONTINUATION": "SELL_ON_RALLY_OR_CONTINUATION",
        "SUPPORT_DECISION_ZONE": "WAIT_BREAKDOWN_OR_RECLAIM",
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

    return (
        f"{symbol} {pressure_grade} pressure. "
        f"Execution {execution_grade}. "
        f"Phase: {phase}. "
        f"Action: {action}. "
        f"Zone: {zone}. "
        f"Side: {execution_side}."
    )


def build_trade_plan(block: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    pressure_grade = block["pressure_grade"]
    chart_phase = snapshot["chart_phase"]
    action = snapshot["action"]

    execution_grade = grade_execution(pressure_grade, chart_phase)
    execution_side = map_execution_side(chart_phase)

    price_at_end = snapshot.get("price_at_end")
    price_text = None
    if price_at_end is not None:
        digit_count = 3 if "JPY" in block["symbol"] else 5
        price_text = f"{float(price_at_end):.{digit_count}f}"

    return {
        "symbol": block["symbol"],
        "signal_type": "SIGNAL_THROTTLE_PRESSURE",
        "pressure_status": pressure_status_from_grade(pressure_grade),
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
        "action": action,
        "entry_zone": snapshot.get("entry_zone"),
        "breakout_level": snapshot.get("breakout_level"),
        "reclaim_level": snapshot.get("reclaim_level"),
        "invalidation": snapshot.get("invalidation"),
        "tp1": snapshot.get("tp1"),
        "tp2": snapshot.get("tp2"),
        "tp3": snapshot.get("tp3"),
        "message": build_message(block, snapshot, execution_grade, execution_side),
        "raw": {
            "block": block,
            "snapshot": {
                key: value
                for key, value in snapshot.items()
                if key != "raw_ohlc"
            },
        },
    }
