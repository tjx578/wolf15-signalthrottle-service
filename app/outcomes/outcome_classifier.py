"""Outcome classification — Phase 4.

Maps MFE/MAE measurements to a discrete result_label so the dashboard
can summarize edge by phase / grade.
"""
from __future__ import annotations


def classify_outcome(
    *,
    mfe_30m: float | None,
    mae_30m: float | None,
    min_good_mfe: float,
    max_good_mae: float,
) -> str:
    if mfe_30m is None or mae_30m is None:
        return "PENDING"

    if mfe_30m >= min_good_mfe and mae_30m <= max_good_mae:
        return "FOLLOW_THROUGH_STRONG"

    if mfe_30m >= min_good_mfe * 0.5 and mae_30m <= max_good_mae * 1.5:
        return "FOLLOW_THROUGH_WEAK"

    if mae_30m > max_good_mae * 2 and mfe_30m < min_good_mfe * 0.5:
        return "REVERSAL_AGAINST_SIGNAL"

    if mfe_30m < min_good_mfe * 0.5 and mae_30m < max_good_mae * 1.5:
        return "NO_FOLLOW_THROUGH"

    return "CHOPPY_NO_EDGE"
