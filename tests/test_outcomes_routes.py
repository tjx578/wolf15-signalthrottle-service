from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_outcome_routes_are_not_mounted() -> None:
    client = TestClient(create_app())

    assert client.get("/outcomes/summary").status_code == 404
    assert client.post("/outcomes/backfill").status_code == 404
