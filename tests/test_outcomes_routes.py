from __future__ import annotations

from fastapi.testclient import TestClient

import app.api.routes_outcomes as routes_outcomes
import app.lifecycle as lifecycle
from app.main import create_app


async def _noop() -> None:
    return None


class FakeSignalRepository:
    async def get_latest_outcomes(self, limit: int = 20) -> list[dict]:
        return []

    async def get_outcome_summary(self) -> dict:
        return {
            "total": 9,
            "strong_pct": 55.56,
            "avg_mfe_30m": 0.0024,
            "avg_mae_30m": 0.0018,
            "best_phase": "PIVOT_RECLAIM_CONTINUATION",
            "worst_phase": "RANGE_MID_NO_EDGE",
            "best_h4_context_type": "FAILED_BREAKOUT_ACCEPTANCE",
            "worst_h4_context_type": "RANGE_EDGE_COMPRESSION",
        }

    async def get_outcomes_by_phase(self) -> list[dict]:
        return []

    async def get_outcomes_by_grade(self) -> list[dict]:
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

    async def get_outcome(self, outcome_id: int) -> dict | None:
        return None


def test_outcomes_by_h4_context_route(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_outcomes, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/outcomes/by-h4-context")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["rows"][0]["h4_context_type"] == "FAILED_BREAKOUT_ACCEPTANCE"
    assert payload["rows"][1]["h4_context_type"] == "RANGE_EDGE_COMPRESSION"


def test_outcomes_summary_includes_best_and_worst_h4_context(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_outcomes, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/outcomes/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["best_h4_context_type"] == "FAILED_BREAKOUT_ACCEPTANCE"
    assert payload["worst_h4_context_type"] == "RANGE_EDGE_COMPRESSION"


def test_outcomes_by_reason_code_route(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_outcomes, "SignalRepository", FakeSignalRepository)

    app = create_app()
    client = TestClient(app)

    response = client.get("/outcomes/by-reason-code")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["rows"][0]["reason_code"] == "UPPER_RANGE_FAILED_EXPANSION"
    assert payload["rows"][1]["reason_code"] == "UPPER_RESISTANCE_REJECTION"