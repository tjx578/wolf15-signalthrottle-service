from __future__ import annotations

from fastapi.testclient import TestClient

import app.api.routes_debug as routes_debug
import app.lifecycle as lifecycle
from app.main import create_app


async def _noop() -> None:
    return None


class FakeSignalRepository:
    async def get_today_signal_debug_counts(self, *, start_utc, end_utc) -> dict:
        return {
            "signal_events_today": 113,
            "engine_source_events_today": 113,
            "active_blocks_today": 1,
            "dashboard_signals_today": 1,
            "latest_signal_event_utc": "2026-04-27T07:24:55.093229+00:00",
        }


def test_debug_sync_endpoint_reports_sync_state(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_debug, "SignalRepository", FakeSignalRepository)
    monkeypatch.setattr(routes_debug.settings, "engine_log_sync_enabled", True)
    monkeypatch.setattr(routes_debug.settings, "engine_log_source_url", "https://example.com/logs")
    monkeypatch.setattr(
        routes_debug,
        "get_last_sync_result",
        lambda: {"status": "ok", "events_stored": 113, "duplicates_skipped": 0},
    )

    app = create_app()
    client = TestClient(app)

    response = client.get("/debug/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["engine_log_sync_enabled"] is True
    assert payload["engine_log_source_configured"] is True
    assert payload["today_counts"]["signal_events_today"] == 113
    assert payload["last_sync_result"]["status"] == "ok"
    assert payload["dashboard_empty_reason"] == "signal_events_exist_today"


def test_debug_sync_endpoint_explains_empty_dashboard(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_debug.settings, "engine_log_sync_enabled", False)
    monkeypatch.setattr(routes_debug.settings, "engine_log_source_url", None)
    monkeypatch.setattr(
        routes_debug,
        "get_last_sync_result",
        lambda: {"status": "disabled"},
    )

    class EmptySignalRepository:
        async def get_today_signal_debug_counts(self, *, start_utc, end_utc) -> dict:
            return {
                "signal_events_today": 0,
                "engine_source_events_today": 0,
                "active_blocks_today": 0,
                "dashboard_signals_today": 0,
                "latest_signal_event_utc": None,
            }

    monkeypatch.setattr(routes_debug, "SignalRepository", EmptySignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/debug/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dashboard_empty_reason"] == "engine_log_sync_disabled"


def test_debug_schema_endpoint_reports_drift(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)

    async def _fake_schema_status() -> dict:
        return {
            "pressure_blocks": {
                "block_hash": False,
                "market_context_status": True,
                "trade_plan_status": False,
                "pending_reason": True,
                "uq_st_pressure_blocks_block_hash": False,
            },
            "table_exists": True,
            "missing_columns": ["block_hash", "trade_plan_status"],
            "missing_indexes": ["uq_st_pressure_blocks_block_hash"],
            "status": "DATABASE_SCHEMA_OUT_OF_SYNC",
        }

    monkeypatch.setattr(routes_debug, "get_pressure_blocks_schema_status", _fake_schema_status)

    app = create_app()
    client = TestClient(app)

    response = client.get("/debug/schema")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "DATABASE_SCHEMA_OUT_OF_SYNC"
    assert payload["pressure_blocks"]["block_hash"] is False
    assert payload["pressure_blocks"]["trade_plan_status"] is False
    assert payload["missing_columns"] == ["block_hash", "trade_plan_status"]
    assert payload["missing_indexes"] == ["uq_st_pressure_blocks_block_hash"]