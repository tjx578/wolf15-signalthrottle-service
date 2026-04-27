from __future__ import annotations

from fastapi.testclient import TestClient

import app.api.routes_signals as routes_signals
import app.lifecycle as lifecycle
from app.main import create_app


async def _noop() -> None:
    return None


class FakeSignalRepository:
    async def get_latest_trade_plans(self, limit: int = 20, bucket: str = "all") -> list[dict]:
        data = {
            "all": [
                {"id": 1, "symbol": "AUDUSD", "execution_grade": "C", "action": "NO_TRADE_WAIT_CONTEXT"},
                {"id": 3, "symbol": "EURUSD", "execution_grade": "B+", "action": "WAIT_BREAKDOWN_OR_RECLAIM"},
                {"id": 2, "symbol": "USDJPY", "execution_grade": "A", "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD"},
            ],
            "actionable": [
                {"id": 2, "symbol": "USDJPY", "execution_grade": "A", "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD"},
            ],
            "watchlist": [
                {"id": 1, "symbol": "AUDUSD", "execution_grade": "C", "action": "NO_TRADE_WAIT_CONTEXT"},
                {"id": 3, "symbol": "EURUSD", "execution_grade": "B+", "action": "WAIT_BREAKDOWN_OR_RECLAIM"},
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
                    "trade_plan_status": "READY",
                    "market_context_status": "READY",
                    "dashboard_bucket": "trade_plan_ready",
                },
            ],
        }
        return data[bucket][:limit]


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