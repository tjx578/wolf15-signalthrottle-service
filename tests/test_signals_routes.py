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
                {"id": 2, "symbol": "USDJPY", "execution_grade": "A", "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD"},
            ],
            "actionable": [
                {"id": 2, "symbol": "USDJPY", "execution_grade": "A", "action": "BUY_ON_RETEST_OR_RECLAIM_HOLD"},
            ],
            "watchlist": [
                {"id": 1, "symbol": "AUDUSD", "execution_grade": "C", "action": "NO_TRADE_WAIT_CONTEXT"},
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
    assert payload["count"] == 2