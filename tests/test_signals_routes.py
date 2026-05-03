from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

import app.api.routes_signals as routes_signals
import app.lifecycle as lifecycle
from app.main import create_app


async def _noop() -> None:
    return None


class FakeSignalRepository:
    async def get_signal_history(self, symbol: str | None = None, limit: int = 50) -> list[dict]:
        data = [
            {
                "id": 12,
                "symbol": "GBPUSD",
                "start_utc": "2026-04-27T07:25:40Z",
                "end_utc": "2026-04-27T07:30:03Z",
                "pressure_grade": "B+",
            },
            {
                "id": 11,
                "symbol": "GBPUSD",
                "start_utc": "2026-04-27T07:15:23Z",
                "end_utc": "2026-04-27T07:25:25Z",
                "pressure_grade": "A-",
            },
        ]
        if symbol:
            data = [row for row in data if row["symbol"] == symbol]
        return data[:limit]

    async def get_signal_series(self, symbol: str | None = None, limit: int = 50) -> list[dict]:
        data = [
            {
                "symbol": "GBPUSD",
                "start_utc": "2026-04-27T07:15:23Z",
                "end_utc": "2026-04-27T07:30:03Z",
                "duration_minutes": 14.67,
                "event_count": 113,
                "density_per_minute": 7.7,
                "max_gap_seconds": 22.0,
                "block_count": 2,
                "latest_block_id": 12,
                "best_pressure_grade": "A-",
                "latest_pressure_grade": "B+",
                "best_valid_block_grade": "A-",
                "series_reason": "SPLIT_BY_CONTINUITY_GAP",
                "series_gap_rule_seconds": 300,
                "block_continuity_rule_seconds": 90,
            }
        ]
        if symbol:
            data = [row for row in data if row["symbol"] == symbol]
        return data[:limit]

    async def get_latest_trade_plans(self, limit: int = 20, bucket: str = "all") -> list[dict]:
        data = {
            "all": [
                {"id": 1, "symbol": "AUDUSD", "execution_grade": "C", "action": "NO_TRADE_WAIT_CONTEXT", "payload": {"snapshot": {}}, "h4_structure": None, "h4_context_type": None},
                {"id": 3, "symbol": "EURUSD", "execution_grade": "B+", "action": "WAIT_BREAKDOWN_OR_RECLAIM", "payload": {"snapshot": {"h4_structure": "BEARISH_EXHAUSTION_RISK", "h4_context_type": "FAILED_BREAKDOWN_ACCEPTANCE"}}},
                {"id": 2, "symbol": "USDJPY", "execution_grade": "A", "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD", "payload": {"snapshot": {"h4_structure": "BULLISH_CONTINUATION", "h4_context_type": "CONTINUATION_TREND"}}},
            ],
            "actionable": [
                {"id": 2, "symbol": "USDJPY", "execution_grade": "A", "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD", "payload": {"snapshot": {"h4_structure": "BULLISH_CONTINUATION", "h4_context_type": "CONTINUATION_TREND"}}},
            ],
            "watchlist": [
                {"id": 1, "symbol": "AUDUSD", "execution_grade": "C", "action": "NO_TRADE_WAIT_CONTEXT", "payload": {"snapshot": {}}, "h4_structure": None, "h4_context_type": None},
                {"id": 3, "symbol": "EURUSD", "execution_grade": "B+", "action": "WAIT_BREAKDOWN_OR_RECLAIM", "payload": {"snapshot": {"h4_structure": "BEARISH_EXHAUSTION_RISK", "h4_context_type": "FAILED_BREAKDOWN_ACCEPTANCE"}}},
            ],
        }
        return data[bucket][:limit]

    async def get_latest_watchlist_signals(self, limit: int = 20) -> list[dict]:
        data = [
            {
                "id": None,
                "trade_plan_id": None,
                "block_id": 7,
                "symbol": "GBPUSD",
                "pressure_grade": "B+",
                "execution_grade": None,
                "action": None,
                "trade_plan_status": "TRADE_PLAN_PENDING",
                "market_context_status": "PENDING",
                "signal_end_wita": "2026-04-27 15:30:03",
            },
            {
                "id": 3,
                "trade_plan_id": 3,
                "block_id": 3,
                "symbol": "EURUSD",
                "pressure_grade": "B+",
                "execution_grade": "B+",
                "action": "WAIT_BREAKDOWN_OR_RECLAIM",
                "trade_plan_status": "TRADE_PLAN_READY",
                "market_context_status": "READY",
                "signal_end_wita": "2026-04-27 15:10:00",
            },
        ]
        return data[:limit]

    async def get_latest_signals(self, limit: int = 50, bucket: str = "watchlist") -> list[dict]:
        data = {
            "all": [
                {
                    "id": None,
                    "trade_plan_id": None,
                    "block_id": 1,
                    "symbol": "EURGBP",
                    "pressure_grade": "C",
                    "execution_grade": None,
                    "action": None,
                    "h4_structure": None,
                    "h4_context_type": None,
                    "trade_plan_status": "NOT_REQUIRED",
                    "market_context_status": "NOT_REQUIRED",
                    "dashboard_bucket": "radar_below_threshold",
                },
                {
                    "id": None,
                    "trade_plan_id": None,
                    "block_id": 7,
                    "symbol": "GBPUSD",
                    "pressure_grade": "B+",
                    "execution_grade": None,
                    "action": None,
                    "h4_structure": "BEARISH_CONTINUATION",
                    "h4_context_type": "CONTINUATION_TREND",
                    "trade_plan_status": "TRADE_PLAN_REQUIRED",
                    "market_context_status": "PENDING_OR_FAILED",
                    "dashboard_bucket": "watchlist_trade_plan_pending",
                },
                {
                    "id": 8,
                    "trade_plan_id": 8,
                    "block_id": 8,
                    "symbol": "EURUSD",
                    "pressure_grade": "A-",
                    "execution_grade": "B+",
                    "action": "WAIT_BREAKDOWN_OR_RECLAIM",
                    "h4_structure": "BEARISH_EXHAUSTION_RISK",
                    "h4_context_type": "FAILED_BREAKDOWN_ACCEPTANCE",
                    "trade_plan_status": "READY",
                    "market_context_status": "READY",
                    "dashboard_bucket": "trade_plan_ready",
                },
                {
                    "id": 2,
                    "trade_plan_id": 2,
                    "block_id": 2,
                    "symbol": "USDJPY",
                    "pressure_grade": "A",
                    "execution_grade": "A",
                    "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD",
                    "h4_structure": "BULLISH_CONTINUATION",
                    "h4_context_type": "CONTINUATION_TREND",
                    "chain_adjusted_grade": "A",
                    "chain_type": "CONTINUATION_PULSE_AFTER_A_PLUS",
                    "execution_mode": "INSTANT_EXECUTION_CANDIDATE",
                    "previous_block_grade": "A+",
                    "previous_block_end_wita": "2026-04-23 13:01:27",
                    "gap_from_previous_minutes": 4.82,
                    "trade_plan_status": "READY",
                    "market_context_status": "READY",
                    "dashboard_bucket": "trade_plan_ready",
                },
            ],
            "radar": [
                {
                    "id": None,
                    "trade_plan_id": None,
                    "block_id": 1,
                    "symbol": "EURGBP",
                    "pressure_grade": "C",
                    "execution_grade": None,
                    "action": None,
                    "h4_structure": None,
                    "h4_context_type": None,
                    "trade_plan_status": "NOT_REQUIRED",
                    "market_context_status": "NOT_REQUIRED",
                    "dashboard_bucket": "radar_below_threshold",
                }
            ],
            "watchlist": [
                {
                    "id": None,
                    "trade_plan_id": None,
                    "block_id": 7,
                    "symbol": "GBPUSD",
                    "pressure_grade": "B+",
                    "execution_grade": None,
                    "action": None,
                    "h4_structure": "BEARISH_CONTINUATION",
                    "h4_context_type": "CONTINUATION_TREND",
                    "trade_plan_status": "TRADE_PLAN_REQUIRED",
                    "market_context_status": "PENDING_OR_FAILED",
                    "dashboard_bucket": "watchlist_trade_plan_pending",
                    "owner_alert": "PENDING",
                },
            ],
            "ready": [
                {
                    "id": 8,
                    "trade_plan_id": 8,
                    "block_id": 8,
                    "symbol": "EURUSD",
                    "pressure_grade": "A-",
                    "execution_grade": "B+",
                    "action": "WAIT_BREAKDOWN_OR_RECLAIM",
                    "h4_structure": "BEARISH_EXHAUSTION_RISK",
                    "h4_context_type": "FAILED_BREAKDOWN_ACCEPTANCE",
                    "trade_plan_status": "READY",
                    "market_context_status": "READY",
                    "dashboard_bucket": "trade_plan_ready",
                },
            ],
            "highlighted": [
                {
                    "id": 8,
                    "trade_plan_id": 8,
                    "block_id": 8,
                    "symbol": "EURUSD",
                    "pressure_grade": "A-",
                    "execution_grade": "B+",
                    "action": "WAIT_BREAKDOWN_OR_RECLAIM",
                    "h4_structure": "BEARISH_EXHAUSTION_RISK",
                    "h4_context_type": "FAILED_BREAKDOWN_ACCEPTANCE",
                    "trade_plan_status": "READY",
                    "market_context_status": "READY",
                    "dashboard_bucket": "trade_plan_ready",
                },
            ],
            "actionable": [
                {
                    "id": 2,
                    "trade_plan_id": 2,
                    "block_id": 2,
                    "symbol": "USDJPY",
                    "pressure_grade": "A",
                    "execution_grade": "A",
                    "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD",
                    "h4_structure": "BULLISH_CONTINUATION",
                    "h4_context_type": "CONTINUATION_TREND",
                    "chain_adjusted_grade": "A",
                    "chain_type": "CONTINUATION_PULSE_AFTER_A_PLUS",
                    "execution_mode": "INSTANT_EXECUTION_CANDIDATE",
                    "previous_block_grade": "A+",
                    "previous_block_end_wita": "2026-04-23 13:01:27",
                    "gap_from_previous_minutes": 4.82,
                    "trade_plan_status": "READY",
                    "market_context_status": "READY",
                    "dashboard_bucket": "trade_plan_ready",
                },
            ],
            "priority": [
                {
                    "id": 2,
                    "trade_plan_id": 2,
                    "block_id": 2,
                    "symbol": "USDJPY",
                    "pressure_grade": "A",
                    "execution_grade": "A",
                    "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD",
                    "h4_structure": "BULLISH_CONTINUATION",
                    "h4_context_type": "CONTINUATION_TREND",
                    "chain_adjusted_grade": "A",
                    "chain_type": "CONTINUATION_PULSE_AFTER_A_PLUS",
                    "execution_mode": "INSTANT_EXECUTION_CANDIDATE",
                    "previous_block_grade": "A+",
                    "previous_block_end_wita": "2026-04-23 13:01:27",
                    "gap_from_previous_minutes": 4.82,
                    "trade_plan_status": "READY",
                    "market_context_status": "READY",
                    "dashboard_bucket": "trade_plan_ready",
                },
            ],
        }
        return data[bucket][:limit]

    async def get_trade_plan(self, signal_id: int) -> dict | None:
        if signal_id != 2:
            return None
        return {
            "id": 2,
            "trade_plan_id": 2,
            "symbol": "USDJPY",
            "execution_grade": "A",
            "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD",
            "reason_code": "PIVOT_RECLAIM_VALID",
            "chain_adjusted_grade": None,
            "chain_type": None,
            "execution_mode": None,
            "payload": {
                "chain_context": {
                    "standalone_grade": "B+",
                    "chain_adjusted_grade": "A",
                    "chain_type": "CONTINUATION_PULSE_AFTER_A_PLUS",
                    "execution_mode": "INSTANT_EXECUTION_CANDIDATE",
                    "previous_block_grade": "A+",
                    "previous_block_end_wita": "2026-04-23 13:01:27",
                    "gap_from_previous_minutes": 4.82,
                },
                "snapshot": {
                    "h4_structure": "BULLISH_CONTINUATION",
                    "h4_context_type": "CONTINUATION_TREND",
                }
            },
        }


def test_latest_signals_supports_bucket_filter(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/latest", params={"bucket": "actionable"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["bucket"] == "actionable"
    assert payload["count"] == 1
    assert payload["signals"][0]["symbol"] == "USDJPY"
    assert payload["signals"][0]["trade_plan_status"] == "READY"
    assert payload["signals"][0]["h4_structure"] == "BULLISH_CONTINUATION"
    assert payload["signals"][0]["h4_context_type"] == "CONTINUATION_TREND"
    assert payload["signals"][0]["chain_adjusted_grade"] == "A"
    assert payload["signals"][0]["chain_type"] == "CONTINUATION_PULSE_AFTER_A_PLUS"
    assert payload["signals"][0]["execution_mode"] == "INSTANT_EXECUTION_CANDIDATE"


def test_latest_signals_invalid_bucket_falls_back_to_all(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/latest", params={"bucket": "invalid"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["bucket"] == "all"
    assert payload["count"] == 4
    assert payload["signals"][0]["symbol"] == "EURGBP"


def test_engine_logs_daily_api_returns_observability_summary(monkeypatch) -> None:
    class EngineLogsRepo:
        last_start_utc = None
        last_end_utc = None

        async def get_engine_logs_daily_summary(self, *, start_utc, end_utc) -> dict:
            self.__class__.last_start_utc = start_utc
            self.__class__.last_end_utc = end_utc
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

    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", EngineLogsRepo)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/engine-logs/daily?date=2026-05-01")

    assert response.status_code == 200
    payload = response.json()
    assert payload["view_mode"] == "PHASE1_UTC_DAILY_REPORT"
    assert payload["window"]["window_rule"] == "[start_utc, end_utc)"
    assert payload["window"]["start_utc"] == "2026-05-01T00:00:00+00:00"
    assert payload["window"]["end_utc"] == "2026-05-02T00:00:00+00:00"
    assert EngineLogsRepo.last_start_utc == datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    assert EngineLogsRepo.last_end_utc == datetime(2026, 5, 2, 0, 0, tzinfo=timezone.utc)
    assert payload["raw_extracted_logs"] == 182
    assert payload["symbols"][0]["symbol"] == "NZDCHF"
    assert payload["symbols"][0]["failure_reason"] == "PARSED_ONLY_NO_PROMOTION"

def test_latest_signals_watchlist_includes_b_plus(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/latest", params={"bucket": "watchlist"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["bucket"] == "watchlist"
    assert payload["count"] == 1
    assert payload["signals"][0]["symbol"] == "GBPUSD"
    assert payload["signals"][0]["trade_plan_status"] == "TRADE_PLAN_REQUIRED"
    assert payload["signals"][0]["execution_grade"] is None
    assert payload["signals"][0]["dashboard_bucket"] == "watchlist_trade_plan_pending"
    assert payload["signals"][0]["owner_alert"] == "PENDING"
    assert payload["signals"][0]["h4_structure"] == "BEARISH_CONTINUATION"
    assert payload["signals"][0]["h4_context_type"] == "CONTINUATION_TREND"


def test_latest_signals_priority_returns_a_grades(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/latest", params={"bucket": "priority"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["bucket"] == "priority"
    assert payload["count"] == 1
    assert payload["signals"][0]["pressure_grade"] == "A"
    assert payload["signals"][0]["dashboard_bucket"] == "trade_plan_ready"
    assert payload["signals"][0]["h4_structure"] == "BULLISH_CONTINUATION"
    assert payload["signals"][0]["h4_context_type"] == "CONTINUATION_TREND"


def test_latest_signals_radar_returns_below_threshold_rows(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/latest", params={"bucket": "radar"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["bucket"] == "radar"
    assert payload["count"] == 1
    assert payload["signals"][0]["symbol"] == "EURGBP"
    assert payload["signals"][0]["dashboard_bucket"] == "radar_below_threshold"
    assert "h4_structure" in payload["signals"][0]
    assert "h4_context_type" in payload["signals"][0]


def test_trade_plans_endpoint_exposes_explicit_h4_structure_contract(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/trade-plans", params={"bucket": "watchlist"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["bucket"] == "watchlist"
    assert payload["count"] == 2
    assert payload["trade_plans"][1]["symbol"] == "EURUSD"
    assert payload["trade_plans"][1]["h4_structure"] == "BEARISH_EXHAUSTION_RISK"
    assert payload["trade_plans"][1]["h4_context_type"] == "FAILED_BREAKDOWN_ACCEPTANCE"


def test_trade_plans_invalid_bucket_falls_back_to_all(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/trade-plans", params={"bucket": "unknown"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["bucket"] == "all"
    assert payload["count"] == 3


def test_signal_detail_exposes_h4_contract_fields(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["h4_structure"] == "BULLISH_CONTINUATION"
    assert payload["h4_context_type"] == "CONTINUATION_TREND"
    assert payload["chain_adjusted_grade"] == "A"
    assert payload["chain_type"] == "CONTINUATION_PULSE_AFTER_A_PLUS"
    assert payload["execution_mode"] == "INSTANT_EXECUTION_CANDIDATE"
    assert payload["gap_from_previous_minutes"] == 4.82


def test_signal_history_returns_raw_block_history(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/history", params={"symbol": "GBPUSD"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["history_type"] == "raw_blocks"
    assert payload["count"] == 2
    assert payload["signals"][0]["id"] == 12


def test_signal_series_returns_merged_pressure_series(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/series", params={"symbol": "GBPUSD"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["history_type"] == "merged_pressure_series"
    assert payload["count"] == 1
    assert payload["signals"][0]["block_count"] == 2
    assert payload["signals"][0]["latest_block_id"] == 12
    assert payload["signals"][0]["series_reason"] == "SPLIT_BY_CONTINUITY_GAP"
    assert payload["signals"][0]["best_valid_block_grade"] == "A-"
    assert payload["signals"][0]["series_gap_rule_seconds"] == 300
    assert payload["signals"][0]["block_continuity_rule_seconds"] == 90
