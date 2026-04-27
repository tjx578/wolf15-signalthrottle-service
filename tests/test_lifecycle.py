from __future__ import annotations

from fastapi.testclient import TestClient

import app.lifecycle as lifecycle
from app.main import create_app


async def _noop() -> None:
    return None


async def _noop_loop(stop_event) -> None:
    return None


def test_lifespan_runs_migrations_after_schema_init_failure(monkeypatch) -> None:
    calls: list[str] = []

    async def _failing_init_db() -> None:
        calls.append("init_db")
        raise RuntimeError('column "block_hash" does not exist')

    async def _run_migrations() -> list[dict]:
        calls.append("run_migrations")
        return [{"name": "_migration_006", "status": "ok"}]

    monkeypatch.setattr(lifecycle, "init_db", _failing_init_db)
    monkeypatch.setattr(lifecycle, "run_migrations", _run_migrations)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(lifecycle, "finalizer_loop", _noop_loop)
    monkeypatch.setattr(lifecycle, "_OUTCOMES_AVAILABLE", False)
    monkeypatch.setattr(lifecycle.settings, "engine_log_sync_enabled", False)

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert calls == ["init_db", "run_migrations"]