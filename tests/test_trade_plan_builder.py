from app.planner.trade_plan_builder import build_trade_plan


def test_build_plan_a_grade():
    block = {
        "symbol": "USDJPY",
        "pressure_grade": "A",
        "start_utc": "2026-04-24T02:00:00Z",
        "end_utc": "2026-04-24T02:15:00Z",
        "start_wita": "2026-04-24 10:00:00",
        "end_wita": "2026-04-24 10:15:00",
        "chart_start_time": "2026-04-24 05:00:00",
        "chart_end_time": "2026-04-24 05:15:00",
        "duration_minutes": 15.0,
        "event_count": 120,
        "density_per_minute": 8.0,
        "max_gap_seconds": 45.0,
        "avg_gap_seconds": 7.5,
        "block_relation": "FIRST_BLOCK",
        "finalize_mode": "SOFT_FINALIZE",
    }
    snapshot = {
        "price_at_end": 143.50,
        "entry_zone": "143.400-143.550",
        "chart_bias": "BULLISH_MACRO_RANGE",
        "chart_phase": "PIVOT_RECLAIM_CONTINUATION",
        "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD",
        "tp1": "143.700",
    }

    result = build_trade_plan(block, snapshot)

    assert result["symbol"] == "USDJPY"
    assert result["pressure_grade"] == "A"
    assert result["execution_grade"] == "A"
    assert result["signal_bucket"] == "actionable"
    assert result["execution_side"] == "BUY_CONTINUATION"
    assert result["payload"]["block"]["symbol"] == "USDJPY"
    assert "USDJPY" in result["message"]


def test_build_plan_c_grade():
    block = {
        "symbol": "EURCHF",
        "pressure_grade": "C",
        "start_utc": "2026-04-24T02:00:00Z",
        "end_utc": "2026-04-24T02:03:00Z",
        "duration_minutes": 3.0,
        "event_count": 5,
        "density_per_minute": 1.5,
    }
    snapshot = {
        "chart_bias": "UNCLASSIFIED",
        "chart_phase": "RANGE_MID_NO_EDGE",
        "action": "NO_TRADE_WAIT_CONTEXT",
    }

    result = build_trade_plan(block, snapshot)

    assert result["execution_grade"] == "C"
    assert result["signal_bucket"] == "watchlist"
    assert result["execution_side"] == "NO_TRADE"


def test_build_plan_b_plus_stays_watchlist() -> None:
    block = {
        "symbol": "GBPUSD",
        "pressure_grade": "A-",
        "start_utc": "2026-04-24T02:00:00Z",
        "end_utc": "2026-04-24T02:11:00Z",
        "duration_minutes": 11.0,
        "event_count": 90,
        "density_per_minute": 8.2,
        "max_gap_seconds": 35.0,
        "avg_gap_seconds": 8.0,
    }
    snapshot = {
        "chart_bias": "SUPPORT_TEST",
        "chart_phase": "SUPPORT_DECISION_ZONE",
        "action": "WAIT_BREAKDOWN_OR_RECLAIM",
        "support_zone": "1.27100-1.27200",
    }

    result = build_trade_plan(block, snapshot)

    assert result["execution_grade"] == "B+"
    assert result["signal_bucket"] == "watchlist"
    assert result["execution_side"] == "WAIT_BREAKDOWN_OR_RECLAIM"


def test_build_plan_b_plus_strong_phase_gets_trade_plan_ready_grade() -> None:
    block = {
        "symbol": "GBPUSD",
        "pressure_grade": "B+",
        "start_utc": "2026-04-27T07:20:36Z",
        "end_utc": "2026-04-27T07:30:03Z",
        "duration_minutes": 9.45,
        "event_count": 113,
        "density_per_minute": 11.96,
        "max_gap_seconds": 14.58,
        "avg_gap_seconds": 5.06,
    }
    snapshot = {
        "price_at_end": 1.27235,
        "entry_zone": "derived_from_structure",
        "invalidation": "derived_from_structure",
        "chart_bias": "BULLISH_RECOVERY",
        "chart_phase": "PULLBACK_TO_SUPPORT",
        "action": "WAIT_SUPPORT_REACTION_OR_RECLAIM",
    }

    result = build_trade_plan(block, snapshot)

    assert result["pressure_grade"] == "B+"
    assert result["execution_grade"] == "B+"
    assert result["signal_bucket"] == "watchlist"
    assert result["action"] == "WAIT_SUPPORT_REACTION_OR_RECLAIM"
    assert result["entry_zone"] == "derived_from_structure"
    assert result["invalidation"] == "derived_from_structure"


def test_build_plan_b_plus_range_mid_stays_wait_state() -> None:
    block = {
        "symbol": "GBPUSD",
        "pressure_grade": "B+",
        "start_utc": "2026-04-27T07:20:36Z",
        "end_utc": "2026-04-27T07:30:03Z",
        "duration_minutes": 9.45,
        "event_count": 113,
        "density_per_minute": 11.96,
    }
    snapshot = {
        "chart_bias": "RANGE",
        "chart_phase": "RANGE_MID_NO_EDGE",
        "action": "NO_TRADE",
    }

    result = build_trade_plan(block, snapshot)

    assert result["execution_grade"] == "C"
    assert result["signal_bucket"] == "watchlist"
    assert result["execution_side"] == "NO_TRADE"
