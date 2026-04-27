from __future__ import annotations

from fastapi.testclient import TestClient

import app.api.routes_webhook as routes_webhook
import app.lifecycle as lifecycle
from app.main import create_app


async def _noop() -> None:
    return None


async def _idle_finalizer(stop_event) -> None:
    await stop_event.wait()


class FakeSignalRepository:
    duplicate = False

    async def insert_signal_event(self, **kwargs) -> dict:
        if self.__class__.duplicate:
            return {"id": 1, "duplicate": True}
        return {"id": 1, "duplicate": False}

    async def upsert_live_block_from_event(self, event, *, max_event_gap_seconds: int, chart_offset_hours: int) -> dict:
        return {
            "id": 42,
            "action": "created",
            "pressure_status": "ACTIVE",
            "pressure_grade": "B+",
        }


def _make_client(monkeypatch) -> TestClient:
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(lifecycle, "finalizer_loop", _idle_finalizer)
    monkeypatch.setattr(routes_webhook, "SignalRepository", FakeSignalRepository)

    app = create_app()
    return TestClient(app)


def test_webhook_log_accepts_and_updates_live_block(monkeypatch) -> None:
    FakeSignalRepository.duplicate = False
    monkeypatch.setattr(routes_webhook.settings, "webhook_secret", "secret")
    client = _make_client(monkeypatch)

    response = client.post(
        "/webhook/log",
        headers={"X-Wolf15-Secret": "secret"},
        json={
            "event": "signal_throttle",
            "symbol": "USDJPY",
            "timestamp_utc": "2026-04-27T02:00:05Z",
            "message": "[SignalThrottle] USDJPY THROTTLED — 3 signals in last 300s (max 3)",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["block_id"] == 42
    assert payload["block_action"] == "created"
    assert payload["pressure_status"] == "ACTIVE"


def test_webhook_log_duplicate_is_ignored(monkeypatch) -> None:
    FakeSignalRepository.duplicate = True
    monkeypatch.setattr(routes_webhook.settings, "webhook_secret", None)
    client = _make_client(monkeypatch)

    response = client.post(
        "/webhook/log",
        json={
            "event": "signal_throttle",
            "symbol": "USDJPY",
            "timestamp_utc": "2026-04-27T02:00:05Z",
            "message": "[SignalThrottle] USDJPY THROTTLED — 3 signals in last 300s (max 3)",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "duplicate_ignored"
    assert payload["symbol"] == "USDJPY"