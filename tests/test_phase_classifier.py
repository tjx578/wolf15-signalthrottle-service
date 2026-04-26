from app.market.phase_classifier import classify_phase


def test_pivot_reclaim():
    result = classify_phase({
        "price": 143.50,
        "pivot_reclaim": True,
        "near_resistance": False,
    })
    assert result["chart_phase"] == "PIVOT_RECLAIM_CONTINUATION"
    assert result["action"] == "BUY_ON_RETEST_OR_RECLAIM_HOLD"


def test_upper_range_exhaustion():
    result = classify_phase({
        "price": 144.00,
        "near_resistance": True,
        "m15_rejection": True,
    })
    assert result["chart_phase"] == "UPPER_RANGE_EXHAUSTION_RISK"


def test_bearish_pullback():
    result = classify_phase({
        "price": 142.00,
        "pullback_active": True,
        "near_support": False,
    })
    assert result["chart_phase"] == "BEARISH_PULLBACK_CONTINUATION"


def test_support_zone():
    result = classify_phase({
        "price": 141.00,
        "near_support": True,
    })
    assert result["chart_phase"] == "SUPPORT_DECISION_ZONE"


def test_unclassified():
    result = classify_phase({"price": 143.00})
    assert result["chart_phase"] == "RANGE_MID_NO_EDGE"
    assert result["action"] == "NO_TRADE_WAIT_CONTEXT"
