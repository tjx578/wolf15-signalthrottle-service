from __future__ import annotations

from app.outcomes.outcome_classifier import classify_outcome


def test_classify_outcome_pending_when_missing():
    assert classify_outcome(mfe_30m=None, mae_30m=0.05, min_good_mfe=0.18, max_good_mae=0.10) == "PENDING"
    assert classify_outcome(mfe_30m=0.20, mae_30m=None, min_good_mfe=0.18, max_good_mae=0.10) == "PENDING"


def test_classify_outcome_strong():
    assert (
        classify_outcome(mfe_30m=0.30, mae_30m=0.05, min_good_mfe=0.18, max_good_mae=0.10)
        == "FOLLOW_THROUGH_STRONG"
    )


def test_classify_outcome_weak():
    # mfe >= 50% of min_good_mfe and mae <= 1.5x max_good_mae
    assert (
        classify_outcome(mfe_30m=0.10, mae_30m=0.12, min_good_mfe=0.18, max_good_mae=0.10)
        == "FOLLOW_THROUGH_WEAK"
    )


def test_classify_outcome_reversal():
    # mae > 2x max_good_mae and mfe < 50% min_good_mfe
    assert (
        classify_outcome(mfe_30m=0.02, mae_30m=0.25, min_good_mfe=0.18, max_good_mae=0.10)
        == "REVERSAL_AGAINST_SIGNAL"
    )


def test_classify_outcome_no_follow_through():
    assert (
        classify_outcome(mfe_30m=0.04, mae_30m=0.05, min_good_mfe=0.18, max_good_mae=0.10)
        == "NO_FOLLOW_THROUGH"
    )


def test_classify_outcome_choppy():
    # mfe between 0.5x and 1x min, mae between 1.5x and 2x max -> falls through to choppy
    assert (
        classify_outcome(mfe_30m=0.12, mae_30m=0.18, min_good_mfe=0.18, max_good_mae=0.10)
        == "CHOPPY_NO_EDGE"
    )
