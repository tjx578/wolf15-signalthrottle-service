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
        "reason_code": "PIVOT_RECLAIM_VALID",
        "primary_scenario": {"action": "BUY_ON_RETEST_OR_RECLAIM_HOLD"},
        "tp1": "143.700",
    }

    result = build_trade_plan(block, snapshot)

    assert result["symbol"] == "USDJPY"
    assert result["pressure_grade"] == "A"
    assert result["execution_grade"] == "A"
    # A pressure + non-WAIT action -> ready bucket (canonical rule).
    assert result["signal_bucket"] == "ready"
    # Owner alert remains restricted to A/A+ + actionable execution.
    assert result["owner_alert"] is True
    assert result["execution_side"] == "BUY_CONTINUATION"
    assert result["reason_code"] == "PIVOT_RECLAIM_VALID"
    assert result["payload"]["scenario_set"]["primary_scenario"]["action"] == "BUY_ON_RETEST_OR_RECLAIM_HOLD"
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
        "reason_code": "RANGE_MID_NO_EDGE",
    }

    result = build_trade_plan(block, snapshot)

    assert result["execution_grade"] == "C"
    assert result["signal_bucket"] == "watchlist"
    assert result["execution_side"] == "NO_TRADE"
    assert result["reason_code"] == "RANGE_MID_NO_EDGE"


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
        "chart_phase": "SUPPORT_REACTION_PENDING",
        "action": "WAIT_SUPPORT_REACTION_OR_RECLAIM",
        "reason_code": "SUPPORT_DECISION_PENDING",
        "support_zone": "1.27100-1.27200",
    }

    result = build_trade_plan(block, snapshot)

    assert result["execution_grade"] == "B+"
    # WAIT-style action keeps signal in watchlist regardless of pressure grade.
    assert result["signal_bucket"] == "watchlist"
    assert result["owner_alert"] is False
    assert result["execution_side"] == "WAIT_SUPPORT_REACTION_OR_RECLAIM"
    assert result["reason_code"] == "SUPPORT_DECISION_PENDING"


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
        "reason_code": "SUPPORT_DECISION_PENDING",
    }

    result = build_trade_plan(block, snapshot)

    assert result["pressure_grade"] == "B+"
    assert result["execution_grade"] == "B+"
    # WAIT_SUPPORT_REACTION_OR_RECLAIM is a wait action so the bucket stays
    # watchlist; the dashboard's SQL CASE will surface this as
    # watchlist_trade_plan_pending if no plan, or trade_plan_ready otherwise.
    assert result["signal_bucket"] == "watchlist"
    assert result["action"] == "WAIT_SUPPORT_REACTION_OR_RECLAIM"
    assert result["entry_zone"] == "derived_from_structure"
    assert result["invalidation"] == "derived_from_structure"
    assert result["reason_code"] == "SUPPORT_DECISION_PENDING"


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
        "reason_code": "RANGE_MID_NO_EDGE",
    }

    result = build_trade_plan(block, snapshot)

    assert result["execution_grade"] == "C"
    assert result["signal_bucket"] == "watchlist"
    assert result["execution_side"] == "NO_TRADE"
    assert result["reason_code"] == "RANGE_MID_NO_EDGE"


def test_build_plan_b_plus_with_actionable_phase_promoted_to_ready() -> None:
    """Canonical rule: B+ pressure with a non-WAIT action must reach the
    'ready' bucket so the dashboard surfaces it. Previously this was
    reserved for A/A+ only, which hid valid B+ plans."""
    block = {
        "symbol": "USDJPY",
        "pressure_grade": "B+",
        "start_utc": "2026-04-24T02:30:34Z",
        "end_utc": "2026-04-24T02:42:50Z",
        "duration_minutes": 12.27,
        "event_count": 95,
        "density_per_minute": 7.74,
        "max_gap_seconds": 38.0,
        "avg_gap_seconds": 7.7,
    }
    snapshot = {
        "price_at_end": 159.42,
        "chart_bias": "BULLISH_MACRO_RANGE",
        "chart_phase": "PIVOT_RECLAIM_CONTINUATION",
        "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD",
        "reason_code": "PIVOT_RECLAIM_VALID",
    }

    result = build_trade_plan(block, snapshot)

    assert result["pressure_grade"] == "B+"
    assert result["signal_bucket"] == "ready"
    assert result["owner_alert"] is False
    assert result["execution_mode"] == "INSTANT_EXECUTION_CANDIDATE"
    assert result["reason_code"] == "PIVOT_RECLAIM_VALID"
    assert "instant buy continuation candidate" in result["message"]


def test_build_plan_range_edge_compression_gets_downgraded_execution_grade() -> None:
    block = {
        "symbol": "USDJPY",
        "pressure_grade": "A-",
        "start_utc": "2026-04-24T02:30:34Z",
        "end_utc": "2026-04-24T02:42:50Z",
        "duration_minutes": 12.27,
        "event_count": 95,
        "density_per_minute": 7.74,
    }
    snapshot = {
        "price_at_end": 159.42,
        "chart_bias": "RANGE_OR_UPPER_PRESSURE",
        "chart_phase": "UPPER_RANGE_EXHAUSTION_RISK",
        "h4_context_type": "RANGE_EDGE_COMPRESSION",
        "action": "PROTECT_LONG_OR_SELL_REJECTION",
        "reason_code": "UPPER_RESISTANCE_REJECTION",
    }

    result = build_trade_plan(block, snapshot)

    assert result["execution_grade"] == "B+"
    assert result["h4_context_type"] == "RANGE_EDGE_COMPRESSION"


def test_build_plan_failed_breakout_acceptance_keeps_stronger_grade() -> None:
    block = {
        "symbol": "USDJPY",
        "pressure_grade": "A-",
        "start_utc": "2026-04-24T02:30:34Z",
        "end_utc": "2026-04-24T02:42:50Z",
        "duration_minutes": 12.27,
        "event_count": 95,
        "density_per_minute": 7.74,
    }
    snapshot = {
        "price_at_end": 159.42,
        "chart_bias": "RANGE_OR_UPPER_PRESSURE",
        "chart_phase": "UPPER_RANGE_EXHAUSTION_RISK",
        "h4_context_type": "FAILED_BREAKOUT_ACCEPTANCE",
        "action": "WAIT_BREAKOUT_OR_REJECTION",
        "reason_code": "UPPER_RANGE_FAILED_EXPANSION",
    }

    result = build_trade_plan(block, snapshot)

    assert result["execution_grade"] == "A"
    assert result["h4_context_type"] == "FAILED_BREAKOUT_ACCEPTANCE"


def test_build_plan_chained_continuation_wait_sets_chain_priority_context() -> None:
    block = {
        "symbol": "NZDCHF",
        "pressure_grade": "B+",
        "start_utc": "2026-04-23T05:06:16Z",
        "end_utc": "2026-04-23T05:15:43Z",
        "start_wita": "2026-04-23 13:06:16",
        "end_wita": "2026-04-23 13:15:43",
        "duration_minutes": 9.44,
        "event_count": 89,
        "density_per_minute": 9.43,
        "max_gap_seconds": 24.27,
        "avg_gap_seconds": 8.1,
        "block_relation": "CHAINED_CONTINUATION",
        "previous_block_grade": "A+",
        "previous_block_end_wita": "2026-04-23 13:01:27",
        "gap_from_previous_minutes": 4.82,
    }
    snapshot = {
        "chart_bias": "SUPPORT_TEST",
        "chart_phase": "SUPPORT_DECISION_ZONE",
        "action": "WAIT_BREAKDOWN_OR_RECLAIM",
        "reason_code": "SUPPORT_DECISION_PENDING",
    }

    result = build_trade_plan(block, snapshot)

    assert result["pressure_status"] == "CHAINED_PRIORITY_PRESSURE"
    assert result["standalone_grade"] == "B+"
    assert result["chain_adjusted_grade"] == "A"
    assert result["chain_type"] == "CONTINUATION_PULSE_AFTER_A_PLUS"
    assert result["execution_mode"] == "INSTANT_IF_CHART_TRIGGER_ACTIVE"
    assert result["execution_grade"] == "B+"
    assert result["signal_bucket"] == "watchlist"
    assert "continuation pulse after A+ block" in result["message"]
    assert result["payload"]["chain_context"]["is_chain_candidate"] is True


def test_build_plan_chained_continuation_actionable_becomes_instant_candidate() -> None:
    block = {
        "symbol": "NZDCHF",
        "pressure_grade": "B+",
        "start_utc": "2026-04-23T05:06:16Z",
        "end_utc": "2026-04-23T05:15:43Z",
        "start_wita": "2026-04-23 13:06:16",
        "end_wita": "2026-04-23 13:15:43",
        "duration_minutes": 9.44,
        "event_count": 89,
        "density_per_minute": 9.43,
        "max_gap_seconds": 24.27,
        "block_relation": "CHAINED_CONTINUATION",
        "previous_block_grade": "A+",
        "previous_block_end_wita": "2026-04-23 13:01:27",
        "gap_from_previous_minutes": 4.82,
    }
    snapshot = {
        "chart_bias": "BULLISH_CONTINUATION",
        "chart_phase": "PIVOT_RECLAIM_CONTINUATION",
        "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD",
        "reason_code": "PIVOT_RECLAIM_VALID",
    }

    result = build_trade_plan(block, snapshot)

    assert result["chain_adjusted_grade"] == "A"
    assert result["execution_mode"] == "INSTANT_EXECUTION_CANDIDATE"
    assert result["execution_grade"] == "A"
    assert result["signal_bucket"] == "ready"
    assert result["owner_alert"] is True


def test_build_plan_nzdchf_business_case_continuation_pulse_after_a_plus() -> None:
    previous_block = {
        "symbol": "NZDCHF",
        "pressure_grade": "A+",
        "start_wita": "2026-04-23 12:36:16",
        "end_wita": "2026-04-23 13:01:27",
        "duration_minutes": 25.01,
        "event_count": 225,
        "density_per_minute": 8.99,
        "max_gap_seconds": 23.48,
    }
    block = {
        "symbol": "NZDCHF",
        "pressure_grade": "B+",
        "start_utc": "2026-04-23T05:06:16Z",
        "end_utc": "2026-04-23T05:15:43Z",
        "start_wita": "2026-04-23 13:06:16",
        "end_wita": "2026-04-23 13:15:43",
        "duration_minutes": 9.44,
        "event_count": 89,
        "density_per_minute": 9.43,
        "max_gap_seconds": 24.27,
        "avg_gap_seconds": 8.1,
        "block_relation": "CHAINED_CONTINUATION",
        "previous_block_grade": previous_block["pressure_grade"],
        "previous_block_end_wita": previous_block["end_wita"],
        "gap_from_previous_minutes": 4.82,
    }
    snapshot = {
        "chart_bias": "SUPPORT_TEST",
        "chart_phase": "SUPPORT_DECISION_ZONE",
        "action": "WAIT_BREAKDOWN_OR_RECLAIM",
        "reason_code": "SUPPORT_DECISION_PENDING",
    }

    result = build_trade_plan(block, snapshot)

    assert result["standalone_grade"] == "B+"
    assert result["chain_adjusted_grade"] == "A"
    assert result["chain_type"] == "CONTINUATION_PULSE_AFTER_A_PLUS"
    assert result["pressure_status"] == "CHAINED_PRIORITY_PRESSURE"
    assert result["execution_mode"] == "INSTANT_IF_CHART_TRIGGER_ACTIVE"
    assert result["previous_block_grade"] == "A+"
    assert result["previous_block_end_wita"] == "2026-04-23 13:01:27"
    assert result["gap_from_previous_minutes"] == 4.82
    assert "Standalone B+, chain-adjusted A" in result["message"]


def test_build_plan_nzdchf3_standalone_bearish_pullback_is_instant_sell_candidate() -> None:
    block = {
        "symbol": "NZDCHF",
        "pressure_grade": "A-",
        "start_utc": "2026-04-23T09:42:03Z",
        "end_utc": "2026-04-23T10:00:17Z",
        "start_wita": "2026-04-23 17:42:03",
        "end_wita": "2026-04-23 18:00:17",
        "duration_minutes": 18.23,
        "event_count": 128,
        "density_per_minute": 7.02,
        "max_gap_seconds": 33.14,
        "avg_gap_seconds": 8.55,
        "block_relation": "NEW_SESSION_SIGNAL",
        "gap_from_previous_minutes": 266.33,
    }
    snapshot = {
        "price_at_end": 0.46174,
        "chart_bias": "TRANSITION_AFTER_RALLY",
        "chart_phase": "BEARISH_PULLBACK_CONTINUATION",
        "h4_context_type": "RANGE_OR_TRANSITION",
        "action": "SELL_ON_RALLY_OR_CONTINUATION",
        "reason_code": "LOWER_HIGH_REJECTION",
        "entry_zone": "0.46114-0.46234",
        "invalidation": "0.46354",
        "tp1": "0.45974",
        "tp2": "0.46020-0.46060",
        "tp3": "0.45674",
    }

    result = build_trade_plan(block, snapshot)

    assert result["chain_type"] is None
    assert result["execution_grade"] == "A"
    assert result["execution_side"] == "SELL_ON_RALLY_OR_CONTINUATION"
    assert result["execution_mode"] == "INSTANT_EXECUTION_CANDIDATE"
    assert result["signal_bucket"] == "ready"
    assert result["owner_alert"] is False
    assert result["price_at_signal_end"] == "0.46174"
    assert result["reason_code"] == "LOWER_HIGH_REJECTION"
    assert "instant sell continuation candidate" in result["message"]
