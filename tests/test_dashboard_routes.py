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
                    "market_context_status": "NOT_REQUIRED",
                    "trade_plan_status": "NOT_REQUIRED",
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
                    "market_context_status": "READY",
                    "trade_plan_status": "READY",
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
                    "chart_phase": "SUPPORT_DECISION_ZONE",
                    "action": "WAIT_BREAKDOWN_OR_RECLAIM",
                    "entry_zone": "1.0710-1.0720",
                    "invalidation": "1.0695",
                    "market_context_status": "READY",
                    "trade_plan_status": "READY",
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
                    "market_context_status": "PENDING_OR_FAILED",
                    "trade_plan_status": "TRADE_PLAN_REQUIRED",
                    "dashboard_bucket": "watchlist_trade_plan_pending",
                    "owner_alert": "PENDING",
                    "display_message": "GBPUSD B+ pressure is valid. Trade plan is required and still pending market-context enrichment.",
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
            "max_gap_seconds": 14.58,
            "message": "GBPUSD B+ pressure with valid market structure. Trade plan shown as watchlist setup.",
            "payload": {"reason": "support reaction setup"},
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
        }

    async def get_outcomes_by_phase(self) -> list[dict]:
        return []

    async def get_outcomes_by_grade(self) -> list[dict]:
        return []

    async def get_latest_outcomes(self, limit: int = 20) -> list[dict]:
        return []


class FakeSignalRepositoryWithBrokenOutcomes(FakeSignalRepository):
    async def get_outcome_summary(self) -> dict:
        raise RuntimeError("signal_outcomes table missing")

    async def get_outcomes_by_phase(self) -> list[dict]:
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
    assert "GBPUSD B+ pressure is valid. Trade plan is required and still pending market-context enrichment." in response.text
    assert "AUDUSD" in response.text
    assert "radar_below_threshold" in response.text
    assert "/signal-detail/2" in response.text
    assert "trade_plan_ready" in response.text
    assert "YES" in response.text


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