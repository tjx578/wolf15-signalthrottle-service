from __future__ import annotations

# Canonical minimum duration (in minutes) for a pressure block to even be
# considered a valid signal candidate. Anything shorter is reported as
# FAILED_MIN_DURATION so dashboards can show it in a separate "failed"
# bucket without confusing it with weak-but-valid C-grade pressure.
MIN_VALID_DURATION_MINUTES = 5.0


def grade_pressure(
    duration: float,
    event_count: int,
    density: float,
    max_gap: float | None,
) -> str:
    if duration < MIN_VALID_DURATION_MINUTES:
        return "FAILED_MIN_DURATION"

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
