from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

import app.api.routes_replay as legacy_replay
import app.main as main


def test_legacy_replay_route_is_not_registered_in_production() -> None:
    client = TestClient(main.create_app())

    response = client.post(
        "/replay/logs",
        json={"logs": "legacy replay attempt"},
        auth=("owner", "secret"),
    )

    assert response.status_code == 404


def test_production_main_does_not_import_legacy_replay() -> None:
    source = inspect.getsource(main)

    assert "routes_replay" not in source
    assert "replay_router" not in source


def test_legacy_replay_module_is_explicitly_quarantined() -> None:
    source = inspect.getsource(legacy_replay)

    assert "LEGACY_UNSAFE_REPLAY" in source
    assert "NOT_FOR_PRODUCTION" in source
    assert "Superseded by the PR-02 durable isolated replay design" in source
