from __future__ import annotations

from fastapi.testclient import TestClient

import app.api.routes_market as routes_market
import app.lifecycle as lifecycle
from app.main import create_app


async def _noop() -> None:
    return None


class FakeFinnhubClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def fetch(
        self,
        symbol: str,
        timeframe: str,
        bars: int = 20,
        end_time_utc=None,
    ) -> list[dict]:
        return [
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "close": 145.11,
            },
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "close": 145.22,
            },
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "close": 145.33,
            },
        ]


def test_market_snapshot_returns_counts_and_latest(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_market, "FinnhubClient", FakeFinnhubClient)
    monkeypatch.setattr(routes_market.settings, "finnhub_api_key", "fake-key")

    app = create_app()
    client = TestClient(app)

    response = client.get("/market/snapshot/USDJPY")

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "USDJPY"
    assert payload["counts"] == {"M15": 3, "H1": 3, "H4": 3, "D1": 3}
    assert payload["latest"]["M15"]["close"] == 145.33
    assert payload["latest"]["H1"]["timeframe"] == "H1"
    assert payload["latest"]["H4"]["symbol"] == "USDJPY"
    assert payload["latest"]["D1"]["close"] == 145.33


def test_market_snapshot_requires_api_key(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_market.settings, "finnhub_api_key", None)

    app = create_app()
    client = TestClient(app)

    response = client.get("/market/snapshot/USDJPY")

    assert response.status_code == 400
    assert response.json()["detail"] == "FINNHUB_API_KEY is not configured"