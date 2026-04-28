from __future__ import annotations

from fastapi.testclient import TestClient

import app.api.routes_dashboard as routes_dashboard
import app.lifecycle as lifecycle
from app.main import create_app


async def _noop() -> None:
    return None


class FakeSignalRepository:
    async def get_active_blocks(self) -> list[dict]:
        return []

    async def get_latest_trade_plans(self, limit: int = 20, bucket: str = "all") -> list[dict]:
        return []

    async def get_latest_watchlist_signals(self, limit: int = 20) -> list[dict]:
        return [
            {
                "id": None,
                "trade_plan_id": None,
                "block_id": 9,
                "symbol": "GBPUSD",
                "pressure_grade": "B+",
                "execution_grade": None,
                "action": None,
                "market_context_status": "PENDING",
                "trade_plan_status": "TRADE_PLAN_PENDING",
                "density_per_minute": 9.65,
                "density_state": "HIGH_DENSITY",
                "signal_end_wita": "2026-04-27 15:30:03",
            }
        ]

    async def get_latest_signals(self, limit: int = 50, bucket: str = "watchlist") -> list[dict]:
        data = {
            "radar": [
                {
                    "id": None,
                    "trade_plan_id": None,
                    "block_id": 1,
                    "symbol": "AUDUSD",
                    "pressure_grade": "C",
                    "execution_grade": None,
                    "chart_phase": None,
                    "action": None,
                    "duration_minutes": 4.2,
                    "event_count": 38,
                    "density_per_minute": 4.15,
                    "density_state": "LOW_DENSITY",
                    "market_context_status": "NOT_REQUIRED",
                    "trade_plan_status": "NOT_REQUIRED",
                    "h4_structure": None,
                    "reason_code": "PRESSURE_BELOW_BPLUS",
                    "dashboard_bucket": "radar_below_threshold",
                    "owner_alert": "NO",
                    "display_message": "AUDUSD C pressure is below B+. Visible as radar only, not yet eligible for trade-plan processing.",
                    "signal_end_wita": "2026-04-27 15:20:03",
                }
            ],
            "ready": [
                {
                    "id": 2,
                    "trade_plan_id": 2,
                    "block_id": 2,
                    "symbol": "USDJPY",
                    "pressure_grade": "A",
                    "execution_grade": "A",
                    "chart_phase": "PIVOT_RECLAIM_CONTINUATION",
                    "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD",
                    "entry_zone": "143.400-143.550",
                    "invalidation": "143.250",
                    "density_per_minute": 11.25,
                    "density_state": "VERY_HIGH_DENSITY",
                    "chain_adjusted_grade": "A",
                    "chain_type": "CONTINUATION_PULSE_AFTER_A_PLUS",
                    "execution_mode": "INSTANT_EXECUTION_CANDIDATE",
                    "h4_structure": "BULLISH_CONTINUATION",
                    "market_context_status": "READY",
                    "trade_plan_status": "READY",
                    "reason_code": "PIVOT_RECLAIM_VALID",
                    "dashboard_bucket": "trade_plan_ready",
                    "owner_alert": "YES",
                    "display_message": "USDJPY A pressure with clean continuation structure. Priority trade plan ready.",
                    "signal_end_wita": "2026-04-27 15:35:03",
                },
                {
                    "id": 8,
                    "trade_plan_id": 8,
                    "block_id": 8,
                    "symbol": "EURUSD",
                    "pressure_grade": "A-",
                    "execution_grade": "B+",
                    "chart_phase": "SUPPORT_REACTION_PENDING",
                    "action": "WAIT_SUPPORT_REACTION_OR_RECLAIM",
                    "entry_zone": "1.0710-1.0720",
                    "invalidation": "1.0695",
                    "density_per_minute": 7.42,
                    "density_state": "HIGH_DENSITY",
                    "h4_structure": "BEARISH_EXHAUSTION_RISK",
                    "market_context_status": "READY",
                    "trade_plan_status": "READY",
                    "reason_code": "SUPPORT_DECISION_PENDING",
                    "dashboard_bucket": "trade_plan_ready",
                    "owner_alert": "OPTIONAL",
                    "display_message": "EURUSD A- pressure with structure confirmation. Highlighted trade plan ready.",
                    "signal_end_wita": "2026-04-27 15:32:03",
                }
            ],
            "watchlist": [
                {
                    "id": None,
                    "trade_plan_id": None,
                    "block_id": 9,
                    "symbol": "GBPUSD",
                    "pressure_grade": "B+",
                    "execution_grade": None,
                    "chart_phase": None,
                    "action": None,
                    "density_per_minute": 9.65,
                    "density_state": "HIGH_DENSITY",
                    "h4_structure": "BEARISH_CONTINUATION",
                    "market_context_status": "PENDING_OR_FAILED",
                    "trade_plan_status": "TRADE_PLAN_REQUIRED",
                    "reason_code": "H4_BEARISH_MASTER_STRUCTURE",
                    "dashboard_bucket": "watchlist_trade_plan_pending",
                    "owner_alert": "PENDING",
                    "display_message": "GBPUSD B+ pressure is valid, but H4 bearish master structure blocks bullish continuation promotion.",
                    "signal_end_wita": "2026-04-27 15:30:03",
                }
            ],
        }
        return data.get(bucket, [])

    async def get_trade_plan(self, signal_id: int) -> dict | None:
        return {
            "id": signal_id,
            "trade_plan_id": signal_id,
            "block_id": 9,
            "symbol": "GBPUSD",
            "pressure_grade": "B+",
            "execution_grade": "B+",
            "action": "WAIT_SUPPORT_REACTION_OR_RECLAIM",
            "duration_minutes": 9.45,
            "event_count": 113,
            "density_per_minute": 11.96,
            "density_state": "VERY_HIGH_DENSITY",
            "max_gap_seconds": 14.58,
            "message": "GBPUSD B+ pressure with valid market structure. Trade plan shown as watchlist setup.",
            "grade_note": "B+ strong density / A- candidate, but duration below 10m",
            "chain_adjusted_grade": None,
            "chain_type": None,
            "execution_mode": None,
            "reason_code": "H4_BEARISH_MASTER_STRUCTURE",
            "h4_structure": "BEARISH_CONTINUATION",
            "payload": {"reason": "support reaction setup", "chain_context": {"standalone_grade": "B+", "chain_adjusted_grade": "A", "chain_type": "CONTINUATION_PULSE_AFTER_A_PLUS", "execution_mode": "INSTANT_IF_CHART_TRIGGER_ACTIVE", "previous_block_grade": "A+", "previous_block_end_wita": "2026-04-23 13:01:27", "gap_from_previous_minutes": 4.82}, "snapshot": {"h4_structure": "BEARISH_CONTINUATION"}, "scenario_set": {"primary_scenario": {"action": "WAIT_SUPPORT_REACTION_OR_RECLAIM"}}},
        }

    async def get_signal_series_detail(self, symbol: str) -> dict | None:
        return {
            "series": {
                "symbol": symbol,
                "start_utc": "2026-04-27T07:15:23Z",
                "end_utc": "2026-04-27T07:30:03Z",
                "duration_minutes": 14.67,
                "event_count": 113,
                "density_per_minute": 7.7,
                "density_state": "HIGH_DENSITY",
                "block_count": 2,
                "best_pressure_grade": "A-",
                "best_valid_block_grade": "A-",
                "latest_pressure_grade": "B+",
                "series_reason": "SPLIT_BY_CONTINUITY_GAP",
                "series_gap_rule_seconds": 300,
                "block_continuity_rule_seconds": 90,
                "pressure_status": "ACTIVE",
                "max_gap_seconds": 22.0,
                "latest_trade_plan_id": 9,
                "grade_note": "High density pressure",
            },
            "raw_signal_events": 113,
            "throttle_states": [
                {
                    "symbol": symbol,
                    "state_start_utc": "2026-04-27T07:15:23Z",
                    "state_end_utc": "2026-04-27T07:30:03Z",
                    "window_seconds": 300,
                    "count_threshold": 3,
                    "log_count": 113,
                    "avg_gap_seconds": 7.86,
                    "max_gap_seconds": 22.0,
                    "duration_minutes": 14.67,
                }
            ],
            "blocks": [
                {
                    "id": 9,
                    "start_utc": "2026-04-27T07:25:40Z",
                    "end_utc": "2026-04-27T07:30:03Z",
                    "pressure_grade": "B+",
                    "event_count": 63,
                    "density_per_minute": 14.38,
                    "density_state": "VERY_HIGH_DENSITY",
                    "duration_minutes": 4.38,
                    "pressure_status": "ACTIVE",
                    "trade_plan_id": 9,
                },
                {
                    "id": 8,
                    "start_utc": "2026-04-27T07:15:23Z",
                    "end_utc": "2026-04-27T07:25:25Z",
                    "pressure_grade": "A-",
                    "event_count": 50,
                    "density_per_minute": 4.99,
                    "density_state": "LOW_DENSITY",
                    "duration_minutes": 10.03,
                    "pressure_status": "SOFT_FINALIZED",
                    "trade_plan_id": None,
                },
            ],
            "trade_plan": {
                "id": 9,
                "trade_plan_id": 9,
                "symbol": symbol,
                "message": "GBPUSD B+ pressure with valid market structure. Trade plan shown as watchlist setup.",
                "reason_code": "H4_BEARISH_MASTER_STRUCTURE",
                "h4_structure": "BEARISH_CONTINUATION",
            },
            "latest_snapshot": {
                "h4_structure": "BEARISH_CONTINUATION",
                "chart_phase": "SUPPORT_REACTION_PENDING",
                "key_level": "1.27200",
                "pivot_mid": 1.272,
                "range_low": 1.271,
                "range_high": 1.273,
                "reclaim_level": 1.272,
                "breakdown_level": 1.271,
                "breakout_level": 1.273,
                "nearest_demand_zone": "1.27100-1.27200",
                "nearest_supply_zone": "1.27280-1.27380",
                "support_zone": "1.27100-1.27200",
                "resistance_zone": "1.27280-1.27380",
            },
        }

    async def get_engine_logs_daily_summary(self, *, start_utc, end_utc) -> dict:
        return {
            "raw_extracted_logs": 182,
            "parsed_signal_events": 182,
            "sync_events": 0,
            "webhook_events": 182,
            "engine_labeled_events": 182,
            "promoted_pressure_blocks": 0,
            "dashboard_signals": 0,
            "symbols": [
                {
                    "symbol": "NZDCHF",
                    "event_count": 107,
                    "first_event_utc": "2026-04-28T08:47:30Z",
                    "last_event_utc": "2026-04-28T10:49:31Z",
                    "sync_event_count": 0,
                    "webhook_event_count": 107,
                    "engine_labeled_event_count": 107,
                    "promoted_blocks": 0,
                    "best_candidate_grade": None,
                    "failure_reason": "PARSED_ONLY_NO_PROMOTION",
                }
            ],
        }

    async def get_dashboard_stats(self) -> dict:
        return {
            "active_blocks": 0,
            "priority_signals": 0,
            "avg_density": "0.0",
            "last_update": "-",
        }

    async def get_outcome_summary(self) -> dict:
        return {
            "total": 0,
            "strong_pct": 0,
            "avg_mfe_30m": 0,
            "avg_mae_30m": 0,
            "best_phase": None,
            "worst_phase": None,
            "best_h4_context_type": "FAILED_BREAKOUT_ACCEPTANCE",
            "worst_h4_context_type": "RANGE_EDGE_COMPRESSION",
        }

    async def get_outcomes_by_phase(self) -> list[dict]:
        return []

    async def get_outcomes_by_h4_context_type(self) -> list[dict]:
        return [
            {
                "h4_context_type": "FAILED_BREAKOUT_ACCEPTANCE",
                "count": 4,
                "strong_count": 3,
                "strong_pct": 75.0,
                "avg_mfe_30m": 0.0042,
                "avg_mae_30m": 0.0011,
            },
            {
                "h4_context_type": "RANGE_EDGE_COMPRESSION",
                "count": 5,
                "strong_count": 1,
                "strong_pct": 20.0,
                "avg_mfe_30m": 0.0013,
                "avg_mae_30m": 0.0024,
            },
        ]

    async def get_outcomes_by_reason_code(self) -> list[dict]:
        return [
            {
                "reason_code": "UPPER_RANGE_FAILED_EXPANSION",
                "count": 4,
                "strong_count": 3,
                "strong_pct": 75.0,
                "avg_mfe_30m": 0.0045,
                "avg_mae_30m": 0.0010,
            },
            {
                "reason_code": "UPPER_RESISTANCE_REJECTION",
                "count": 5,
                "strong_count": 1,
                "strong_pct": 20.0,
                "avg_mfe_30m": 0.0012,
                "avg_mae_30m": 0.0026,
            },
        ]

    async def get_outcomes_by_grade(self) -> list[dict]:
        return []

    async def get_latest_outcomes(self, limit: int = 20) -> list[dict]:
        return [
            {
                "symbol": "USDJPY",
                "chart_phase": "UPPER_RANGE_EXHAUSTION_RISK",
                "h4_context_type": "FAILED_BREAKOUT_ACCEPTANCE",
                "execution_side": "SELL_ON_RALLY_OR_CONTINUATION",
                "price_at_signal": 159.42,
                "mfe_30m": 0.0042,
                "mae_30m": 0.0011,
                "result_label": "FOLLOW_THROUGH_STRONG",
            }
        ]


class FakeSignalRepositoryWithBrokenOutcomes(FakeSignalRepository):
    async def get_outcome_summary(self) -> dict:
        raise RuntimeError("signal_outcomes table missing")

    async def get_outcomes_by_phase(self) -> list[dict]:
        raise RuntimeError("signal_outcomes table missing")

    async def get_outcomes_by_h4_context_type(self) -> list[dict]:
        raise RuntimeError("signal_outcomes table missing")

    async def get_outcomes_by_reason_code(self) -> list[dict]:
        raise RuntimeError("signal_outcomes table missing")

    async def get_outcomes_by_grade(self) -> list[dict]:
        raise RuntimeError("signal_outcomes table missing")

    async def get_latest_outcomes(self, limit: int = 20) -> list[dict]:
        raise RuntimeError("signal_outcomes table missing")


def test_dashboard_watchlist_renders_pending_pressure_without_trade_plan(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_dashboard, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Radar / Below Threshold" in response.text
    assert "Watchlist / Trade Plan Pending" in response.text
    assert "Trade Plan Ready" in response.text
    assert "GBPUSD" in response.text
    assert "watchlist_trade_plan_pending" in response.text
    assert "PENDING" in response.text
    assert "TRADE_PLAN_REQUIRED" in response.text
    assert "H4_BEARISH_MASTER_STRUCTURE" in response.text
    assert "BEARISH_CONTINUATION" in response.text
    assert "GBPUSD B+ pressure is valid, but H4 bearish master structure blocks bullish continuation promotion." in response.text
    assert "AUDUSD" in response.text
    assert "radar_below_threshold" in response.text
    assert "Density State" in response.text
    assert "HIGH_DENSITY" in response.text
    assert "Chain Grade" in response.text
    assert "Execution Mode" in response.text
    assert "INSTANT_EXECUTION_CANDIDATE" in response.text
    assert "/series-detail/GBPUSD" in response.text
    assert "/series-detail/USDJPY" in response.text
    assert "trade_plan_ready" in response.text
    assert "YES" in response.text
    assert "Performance by H4 Context" in response.text
    assert "FAILED_BREAKOUT_ACCEPTANCE" in response.text
    assert "RANGE_EDGE_COMPRESSION" in response.text
    assert "Performance by Reason Code" in response.text
    assert "UPPER_RANGE_FAILED_EXPANSION" in response.text
    assert "UPPER_RESISTANCE_REJECTION" in response.text
    assert "Best H4 Context" in response.text
    assert "Worst H4 Context" in response.text


def test_signal_detail_shows_rationale_summary(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_dashboard, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signal-detail/9")

    assert response.status_code == 200
    assert "Rationale" in response.text
    assert "GBPUSD B+ pressure with valid market structure. Trade plan shown as watchlist setup." in response.text
    assert "H4 Structure" in response.text
    assert "Density State" in response.text
    assert "VERY_HIGH_DENSITY" in response.text
    assert "B+ strong density / A- candidate, but duration below 10m" in response.text
    assert "Chain Adjusted Grade" in response.text
    assert "Chain Type" in response.text
    assert "INSTANT_IF_CHART_TRIGGER_ACTIVE" in response.text
    assert "H4 Promotion Gate" in response.text
    assert "BEARISH_CONTINUATION" in response.text
    assert "/series-detail/GBPUSD" in response.text


def test_series_detail_shows_merged_series_and_raw_blocks(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_dashboard, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/series-detail/GBPUSD")

    assert response.status_code == 200
    assert "Pressure Series Detail" in response.text
    assert "Blocks Merged" in response.text
    assert "Density" in response.text
    assert "Density State" in response.text
    assert "7.7 event/min" in response.text
    assert "HIGH_DENSITY" in response.text
    assert "Throttle State Summary" in response.text
    assert "Raw Signal Events" in response.text
    assert "Throttle State Rows" in response.text
    assert "113" in response.text
    assert "Raw Block History" in response.text
    assert "Latest Market Snapshot" in response.text
    assert "H4 Promotion Gate" in response.text
    assert "BEARISH_CONTINUATION" in response.text
    assert "Best Valid Block Grade" in response.text
    assert "SPLIT_BY_CONTINUITY_GAP" in response.text
    assert "Series Gap Rule" in response.text
    assert "Continuity Block Rule" in response.text
    assert "Plan 9" in response.text
    assert "2026-04-27T07:15:23Z" in response.text


def test_engine_logs_daily_page_shows_observability_summary(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_dashboard, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/engine-logs/daily")

    assert response.status_code == 200
    assert "Engine Logs Daily" in response.text
    assert "Raw Extracted Logs" in response.text
    assert "Parsed Signal Events" in response.text
    assert "PARSED_ONLY_NO_PROMOTION" in response.text
    assert "NZDCHF" in response.text


def test_dashboard_keeps_signals_when_outcome_queries_fail(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_dashboard, "SignalRepository", FakeSignalRepositoryWithBrokenOutcomes)

    app = create_app()
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "GBPUSD" in response.text
    assert "watchlist_trade_plan_pending" in response.text
    assert "No outcome data yet" in response.text
    assert "No H4 context outcome data yet" in response.text
    assert "No reason-code outcome data yet" in response.text
    assert "Best H4 Context" in response.text