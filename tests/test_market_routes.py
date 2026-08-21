from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_market_snapshot_routes_are_not_mounted() -> None:
    client = TestClient(create_app())

    assert client.get("/market/snapshot/USDJPY").status_code == 404
