from __future__ import annotations


def grade_execution(
    pressure_grade: str,
    chart_phase: str | None,
) -> str:
    """Combine pressure grade + chart phase into execution grade."""
    tradeable_phases = {
        "PIVOT_RECLAIM_CONTINUATION",
        "UPPER_RANGE_EXHAUSTION_RISK",
        "BEARISH_PULLBACK_CONTINUATION",
    }

    if pressure_grade in {"A", "A+"} and chart_phase in tradeable_phases:
        return "A"

    if pressure_grade in {"A", "A+", "A-"} and chart_phase in tradeable_phases:
        return "B+"

    if pressure_grade in {"A", "A+", "A-", "B+"}:
        return "B"

    return "C"
