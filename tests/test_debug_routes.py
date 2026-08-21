from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_debug_routes_are_not_mounted() -> None:
    client = TestClient(create_app())

    for path in ("/debug/sync", "/debug/schema", "/debug/engine-logs"):
        assert client.get(path).status_code == 404
