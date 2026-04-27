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
        "h4": _candles([138 + (index * 0.12) for index in range(60)]),
        "h1": _candles([143.2 + (index * 0.02) for index in range(60)]),
        "m15": rejection,
        "near_resistance": True,
        "resistance": 144.1,
        "resistance_zone": "144.020-144.180",
        "support_zone": "143.500-143.660",
    })
    assert result["chart_phase"] == "UPPER_RANGE_EXHAUSTION_RISK"
    assert result["reason_code"] == "UPPER_RESISTANCE_REJECTION"
    assert result["h4_context_type"] == "TERMINAL_REJECTION"


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


def test_h4_bearish_master_structure_blocks_bullish_reclaim_continuation() -> None:
    h1 = _candles(([151.0] * 20) + [150.0, 149.8, 149.6, 149.4, 149.2, 151.0])
    m15 = _candles([149.8 + (index * 0.01) for index in range(30)])
    h4 = _candles([154 - (index * 0.08) for index in range(60)])

    result = classify_phase({
        "symbol": "USDJPY",
        "price": 150.8,
        "d1": _candles([145 + (index * 0.1) for index in range(60)]),
        "h4": h4,
        "h1": h1,
        "m15": m15,
        "near_resistance": False,
        "support_zone": "149.900-150.100",
        "resistance_zone": "151.000-151.080",
    })

    assert result["h4_structure"] == "BEARISH_CONTINUATION"
    assert result["chart_phase"] == "RANGE_MID_NO_EDGE"
    assert result["action"] == "NO_TRADE_WAIT_CONTEXT"
    assert result["reason_code"] == "H4_BEARISH_MASTER_STRUCTURE"


def test_h4_bullish_master_structure_blocks_bearish_pullback_continuation() -> None:
    h1 = _candles([150 - (index * 0.05) for index in range(60)])
    h4 = _candles([141 + (index * 0.08) for index in range(60)])

    result = classify_phase({
        "symbol": "USDJPY",
        "price": 142.00,
        "d1": _candles([148 + (index * 0.03) for index in range(60)]),
        "h4": h4,
        "h1": h1,
        "m15": _candles([143 - (index * 0.02) for index in range(60)]),
        "near_support": False,
        "resistance_zone": "142.500-142.700",
        "support_zone": "141.500-141.660",
    })

    assert result["h4_structure"] == "BULLISH_CONTINUATION"
    assert result["chart_phase"] == "RANGE_MID_NO_EDGE"
    assert result["action"] == "NO_TRADE_WAIT_CONTEXT"
    assert result["reason_code"] == "H4_BULLISH_MASTER_STRUCTURE"


def test_h4_bullish_exhaustion_risk_detected_near_resistance() -> None:
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
        "h4": _candles([138 + (index * 0.12) for index in range(60)]),
        "h1": _candles([143.2 + (index * 0.02) for index in range(60)]),
        "m15": rejection,
        "near_resistance": True,
        "resistance": 144.1,
        "resistance_zone": "144.020-144.180",
        "support_zone": "143.500-143.660",
    })

    assert result["h4_structure"] == "BULLISH_EXHAUSTION_RISK"
    assert result["chart_phase"] == "UPPER_RANGE_EXHAUSTION_RISK"
    assert result["h4_context_type"] == "TERMINAL_REJECTION"


def test_h4_bullish_failed_expansion_has_precise_reason_code() -> None:
    m15 = _candles([143.90, 144.05, 144.02, 143.99, 143.96, 143.94], start_open=143.85)
    m15[-5]["high"] = 144.15
    m15[-4]["high"] = 144.18
    m15[-3]["high"] = 144.14
    result = classify_phase({
        "symbol": "USDJPY",
        "price": 143.94,
        "d1": _candles([141 + (index * 0.08) for index in range(60)]),
        "h4": _candles([138 + (index * 0.12) for index in range(60)]),
        "h1": _candles([143.2 + (index * 0.02) for index in range(60)]),
        "m15": m15,
        "near_resistance": True,
        "resistance": 144.1,
        "breakout_level": 144.1,
        "resistance_zone": "144.020-144.180",
        "support_zone": "143.500-143.660",
    })

    assert result["h4_structure"] == "BULLISH_EXHAUSTION_RISK"
    assert result["chart_phase"] == "UPPER_RANGE_EXHAUSTION_RISK"
    assert result["reason_code"] == "UPPER_RANGE_FAILED_EXPANSION"
    assert result["h4_context_type"] == "FAILED_BREAKOUT_ACCEPTANCE"


def test_h4_bearish_exhaustion_risk_detected_near_support() -> None:
    support_reaction = _candles([141.0, 140.9, 141.05], start_open=141.1)
    support_reaction[-1] = {
        "open": 140.95,
        "high": 141.10,
        "low": 140.70,
        "close": 141.05,
        "timestamp": 3,
    }
    result = classify_phase({
        "symbol": "USDJPY",
        "price": 141.00,
        "d1": _candles([145 - (index * 0.03) for index in range(60)]),
        "h4": _candles([145 - (index * 0.08) for index in range(60)]),
        "h1": _candles([141.2 - (index * 0.01) for index in range(60)]),
        "m15": support_reaction,
        "near_support": True,
        "support_zone": "140.920-141.080",
    })

    assert result["h4_structure"] == "BEARISH_EXHAUSTION_RISK"
    assert result["chart_phase"] == "SUPPORT_REACTION_PENDING"
    assert result["h4_context_type"] == "TERMINAL_REJECTION"


def test_h4_bearish_failed_expansion_has_precise_reason_code() -> None:
    m15 = _candles([141.10, 140.98, 141.00, 141.03, 141.05, 141.08], start_open=141.12)
    m15[-5]["low"] = 140.88
    m15[-4]["low"] = 140.86
    m15[-3]["low"] = 140.90
    result = classify_phase({
        "symbol": "USDJPY",
        "price": 141.08,
        "d1": _candles([145 - (index * 0.03) for index in range(60)]),
        "h4": _candles([145 - (index * 0.08) for index in range(60)]),
        "h1": _candles([141.2 - (index * 0.01) for index in range(60)]),
        "m15": m15,
        "near_support": True,
        "support": 140.92,
        "breakdown_level": 140.92,
        "support_zone": "140.920-141.080",
    })

    assert result["h4_structure"] == "BEARISH_EXHAUSTION_RISK"
    assert result["chart_phase"] == "SUPPORT_REACTION_PENDING"
    assert result["reason_code"] == "LOWER_RANGE_FAILED_EXPANSION"
    assert result["h4_context_type"] == "FAILED_BREAKDOWN_ACCEPTANCE"


def test_h4_range_edge_compression_gets_semantic_context_type() -> None:
    h4 = _candles([138 + (index * 0.12) for index in range(60)])
    m15 = [
        {"open": 144.00, "high": 144.08, "low": 143.98, "close": 144.04, "timestamp": 1},
        {"open": 144.04, "high": 144.09, "low": 144.00, "close": 144.06, "timestamp": 2},
        {"open": 144.06, "high": 144.10, "low": 144.02, "close": 144.07, "timestamp": 3},
        {"open": 144.07, "high": 144.11, "low": 144.03, "close": 144.08, "timestamp": 4},
        {"open": 144.08, "high": 144.10, "low": 144.04, "close": 144.07, "timestamp": 5},
        {"open": 144.07, "high": 144.09, "low": 144.03, "close": 144.08, "timestamp": 6},
        {"open": 144.08, "high": 144.10, "low": 144.05, "close": 144.09, "timestamp": 7},
        {"open": 144.09, "high": 144.10, "low": 144.06, "close": 144.09, "timestamp": 8},
    ]
    result = classify_phase({
        "symbol": "USDJPY",
        "price": 144.09,
        "d1": _candles([141 + (index * 0.08) for index in range(60)]),
        "h4": h4,
        "h1": _candles([143.7 + (index * 0.01) for index in range(60)]),
        "m15": m15,
        "near_resistance": True,
        "resistance": 144.1,
        "breakout_level": 144.1,
        "resistance_zone": "144.020-144.180",
        "support_zone": "143.500-143.660",
    })

    assert result["h4_structure"] == "BULLISH_EXHAUSTION_RISK"
    assert result["h4_context_type"] == "RANGE_EDGE_COMPRESSION"
