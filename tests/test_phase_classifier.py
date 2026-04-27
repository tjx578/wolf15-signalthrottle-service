from app.market.phase_classifier import classify_phase


def _candles(closes: list[float], start_open: float | None = None) -> list[dict]:
    candles = []
    previous = start_open or closes[0]
    for index, close in enumerate(closes):
        open_ = previous
        high = max(open_, close) + 0.05
        low = min(open_, close) - 0.05
        candles.append(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "timestamp": index,
            }
        )
        previous = close
    return candles


def test_pivot_reclaim():
    h1 = _candles(([151.0] * 20) + [150.0, 149.8, 149.6, 149.4, 149.2, 151.0])
    m15 = _candles([149.8 + (index * 0.01) for index in range(30)])
    result = classify_phase({
        "symbol": "USDJPY",
        "price": 150.8,
        "d1": _candles([145 + (index * 0.1) for index in range(60)]),
        "h1": h1,
        "m15": m15,
        "near_resistance": False,
        "resistance_zone": "151.000-151.080",
    })
    assert result["chart_phase"] == "PIVOT_RECLAIM_CONTINUATION"
    assert result["action"] == "BUY_ON_RETEST_OR_RECLAIM_HOLD"
    assert result["reason_code"] == "PIVOT_RECLAIM_VALID"
    assert result["primary_scenario"]["action"] == "BUY_ON_RETEST_OR_RECLAIM_HOLD"


def test_upper_range_exhaustion():
    rejection = _candles([144.0, 144.1, 143.95], start_open=143.8)
    rejection[-1] = {
        "open": 144.0,
        "high": 144.4,
        "low": 143.9,
        "close": 143.95,
        "timestamp": 3,
    }
    result = classify_phase({
        "symbol": "USDJPY",
        "price": 144.00,
        "d1": _candles([141 + (index * 0.08) for index in range(60)]),
        "h1": _candles([143.2 + (index * 0.02) for index in range(60)]),
        "m15": rejection,
        "near_resistance": True,
        "resistance": 144.1,
        "resistance_zone": "144.020-144.180",
        "support_zone": "143.500-143.660",
    })
    assert result["chart_phase"] == "UPPER_RANGE_EXHAUSTION_RISK"
    assert result["reason_code"] == "UPPER_RESISTANCE_REJECTION"


def test_bearish_pullback():
    h1 = _candles([150 - (index * 0.05) for index in range(60)])
    result = classify_phase({
        "symbol": "USDJPY",
        "price": 142.00,
        "d1": _candles([148 + (index * 0.03) for index in range(60)]),
        "h1": h1,
        "m15": _candles([143 - (index * 0.02) for index in range(60)]),
        "near_support": False,
        "support_zone": "141.500-141.660",
    })
    assert result["chart_phase"] == "BEARISH_PULLBACK_CONTINUATION"
    assert result["reason_code"] == "LOWER_HIGH_REJECTION"


def test_support_zone():
    result = classify_phase({
        "symbol": "USDJPY",
        "price": 141.00,
        "d1": _candles([141 + (index * 0.02) for index in range(60)]),
        "h1": _candles([141.2 - (index * 0.01) for index in range(60)]),
        "m15": _candles([141.1 - (index * 0.005) for index in range(40)]),
        "near_support": True,
        "support_zone": "140.920-141.080",
    })
    assert result["chart_phase"] == "SUPPORT_REACTION_PENDING"
    assert result["reason_code"] == "SUPPORT_DECISION_PENDING"


def test_unclassified():
    result = classify_phase({
        "symbol": "EURUSD",
        "price": 1.083,
        "d1": _candles([1.08 + (index * 0.0001) for index in range(60)]),
        "h1": _candles([1.082 + ((-1) ** index) * 0.0002 for index in range(30)]),
        "m15": _candles([1.083 + ((-1) ** index) * 0.0001 for index in range(20)]),
    })
    assert result["chart_phase"] == "RANGE_MID_NO_EDGE"
    assert result["action"] == "NO_TRADE_WAIT_CONTEXT"
    assert result["reason_code"] == "RANGE_MID_NO_EDGE"


def test_upper_range_distribution_without_rejection() -> None:
    result = classify_phase({
        "symbol": "USDJPY",
        "price": 144.05,
        "d1": _candles([141 + (index * 0.08) for index in range(60)]),
        "h1": _candles([143.2 + (index * 0.02) for index in range(60)]),
        "m15": _candles([143.90, 144.00, 144.05, 144.02, 144.04]),
        "near_resistance": True,
        "resistance": 144.1,
        "resistance_zone": "144.020-144.180",
        "support_zone": "143.500-143.660",
    })
    assert result["chart_phase"] == "UPPER_RANGE_DISTRIBUTION"
    assert result["action"] == "WAIT_BREAKOUT_OR_REJECTION"
    assert result["reason_code"] == "UPPER_RANGE_DISTRIBUTION"
