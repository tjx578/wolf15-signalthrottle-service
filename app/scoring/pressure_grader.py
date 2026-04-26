from __future__ import annotations


def grade_pressure(
    duration: float,
    event_count: int,
    density: float,
    max_gap: float | None,
) -> str:
    if max_gap is None:
        return "C"

    if max_gap > 300:
        return "REJECT"

    if duration >= 20 and event_count >= 150 and density >= 7 and max_gap <= 60:
        return "A+"

    if duration >= 14 and event_count >= 100 and density >= 7 and max_gap <= 60:
        return "A"

    if duration >= 10 and density >= 7 and max_gap <= 60:
        return "A-"

    if duration >= 5 and density >= 5 and max_gap <= 90:
        return "B+"

    return "C"
