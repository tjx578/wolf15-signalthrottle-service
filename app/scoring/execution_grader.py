from __future__ import annotations


def grade_execution(
    pressure_grade: str,
    chart_phase: str | None,
    h4_context_type: str | None = None,
) -> str:
    """Combine pressure grade + chart phase into execution grade."""
    tradeable_phases = {
        "PIVOT_RECLAIM_CONTINUATION",
        "UPPER_RANGE_EXHAUSTION_RISK",
        "BEARISH_PULLBACK_CONTINUATION",
    }

    def _downgrade(base_grade: str) -> str:
        if h4_context_type == "RANGE_EDGE_COMPRESSION":
            return {"A": "B+", "B+": "B", "B": "C"}.get(base_grade, base_grade)
        return base_grade

    if pressure_grade in {"A", "A+"} and chart_phase in tradeable_phases:
        return _downgrade("A")

    if pressure_grade in {"A", "A+", "A-"} and chart_phase in tradeable_phases:
        return _downgrade("B+")

    if pressure_grade in {"A", "A+", "A-", "B+"}:
        return _downgrade("B")

    return "C"
