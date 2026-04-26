from __future__ import annotations


def classify_block_relation(
    gap_minutes: float | None,
    previous_grade: str | None = None,
) -> str:
    if gap_minutes is None:
        return "FIRST_BLOCK"

    if gap_minutes <= 10 and previous_grade in {"A", "A+"}:
        return "CHAINED_CONTINUATION"

    if gap_minutes <= 30:
        return "SAME_PRESSURE_SEQUENCE"

    if gap_minutes <= 90:
        return "SAME_SESSION_RECHECK"

    return "NEW_SESSION_SIGNAL"
