from __future__ import annotations


def compute_final_score(
    pressure_grade: str,
    execution_grade: str,
) -> dict:
    """Return a combined readability score dict."""
    grade_rank = {"A+": 6, "A": 5, "A-": 4, "B+": 3, "B": 2, "C": 1, "REJECT": 0}

    p = grade_rank.get(pressure_grade, 1)
    e = grade_rank.get(execution_grade, 1)

    is_priority = p >= 5 and e >= 5

    return {
        "pressure_rank": p,
        "execution_rank": e,
        "combined_rank": p + e,
        "is_priority": is_priority,
    }
