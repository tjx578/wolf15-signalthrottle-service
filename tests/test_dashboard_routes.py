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
            "priority": [
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
                    "dashboard_bucket": "priority_tradeplan",
                    "owner_alert": "YES",
                    "display_message": "USDJPY A pressure with clean continuation structure. Priority trade plan ready.",
                    "signal_end_wita": "2026-04-27 15:35:03",
                }
            ],
            "actionable": [
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
                    "dashboard_bucket": "highlighted_tradeplan",
                    "owner_alert": "OPTIONAL",
                    "display_message": "EURUSD A- pressure with structure confirmation. Highlighted trade plan ready.",
                    "signal_end_wita": "2026-04-27 15:32:03",
                }
            ],
            "watchlist": [
                {
                    "id": 9,
                    "trade_plan_id": 9,
                    "block_id": 9,
                    "symbol": "GBPUSD",
                    "pressure_grade": "B+",
                    "execution_grade": "B+",
                    "chart_phase": "PULLBACK_TO_SUPPORT",
                    "action": "WAIT_SUPPORT_REACTION_OR_RECLAIM",
                    "market_context_status": "READY",
                    "trade_plan_status": "READY",
                    "dashboard_bucket": "watchlist_tradeplan",
                    "owner_alert": "OPTIONAL",
                    "display_message": "GBPUSD B+ pressure with valid market structure. Trade plan shown as watchlist setup.",
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
    assert "Priority Trade Plans" in response.text
    assert "Actionable Trade Plans" in response.text
    assert "GBPUSD" in response.text
    assert "watchlist_tradeplan" in response.text
    assert "OPTIONAL" in response.text
    assert "WAIT_SUPPORT_REACTION_OR_RECLAIM" in response.text
    assert "GBPUSD B+ pressure with valid market structure. Trade plan shown as watchlist setup." in response.text
    assert "/signal-detail/9" in response.text
    assert "priority_tradeplan" in response.text
    assert "highlighted_tradeplan" in response.text
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
    assert "watchlist_tradeplan" in response.text
    assert "No outcome data yet" in response.text