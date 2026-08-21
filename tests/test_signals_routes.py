from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient as RawTestClient

import app.api.routes_signals as routes_signals
import app.lifecycle as lifecycle
from app.main import create_app


def TestClient(app):
    return RawTestClient(
        app,
        headers={"Authorization": "Basic b3duZXI6c2VjcmV0"},
    )


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

    async def get_latest_pressure_observations(
        self, limit: int = 50, bucket: str = "all"
    ) -> list[dict]:
        if bucket in {"failed", "active"}:
            return []
        rows = await self.get_latest_signals(limit=limit, bucket=bucket)
        observations = []
        for row in rows:
            observations.append(
                {
                    "id": row["block_id"],
                    "block_id": row["block_id"],
                    "symbol": row["symbol"],
                    "pressure_grade": row["pressure_grade"],
                    "observation_bucket": bucket,
                    "source_authority": "LEGACY_OBSERVATIONAL",
                    "raw_coverage": "RAW_COVERAGE_UNKNOWN",
                    "expected_pair_admission": "NOT_EVALUATED",
                    "consumer_authority": "OBSERVATIONAL_ONLY",
                    "valid_for_execution": False,
                    "execution_command_allowed": False,
                }
            )
        return observations

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


def test_latest_observations_supports_priority_bucket(monkeypatch) -> None:
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
    assert payload["observer_mode"] == "OBSERVE_ONLY"
    assert payload["containment_profile"] == "PHASE1_OBSERVE_ONLY"
    assert payload["observations"][0]["symbol"] == "USDJPY"
    assert payload["observations"][0]["consumer_authority"] == "OBSERVATIONAL_ONLY"
    assert payload["observations"][0]["source_authority"] == "LEGACY_OBSERVATIONAL"
    assert payload["observations"][0]["valid_for_execution"] is False
    assert "h4_structure" not in payload["observations"][0]


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
    assert payload["observations"][0]["symbol"] == "EURGBP"


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

def test_latest_signals_legacy_watchlist_bucket_falls_back_to_all(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/latest", params={"bucket": "watchlist"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["bucket"] == "all"
    assert payload["count"] == 4
    assert all(
        item["execution_command_allowed"] is False
        for item in payload["observations"]
    )


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
    assert payload["observations"][0]["pressure_grade"] == "A"
    assert payload["observations"][0]["expected_pair_admission"] == "NOT_EVALUATED"
    assert "execution_grade" not in payload["observations"][0]


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
    assert payload["observations"][0]["symbol"] == "EURGBP"
    assert payload["observations"][0]["observation_bucket"] == "radar"
    assert "h4_structure" not in payload["observations"][0]
    assert "h4_context_type" not in payload["observations"][0]


def test_trade_plans_endpoint_is_not_mounted(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/trade-plans", params={"bucket": "watchlist"})

    assert response.status_code == 404


def test_trade_plans_endpoint_remains_absent_for_any_query(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/trade-plans", params={"bucket": "unknown"})

    assert response.status_code == 404


def test_signal_detail_endpoint_is_not_mounted(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/signals/2")

    assert response.status_code == 404


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
