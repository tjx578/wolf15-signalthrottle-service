from __future__ import annotations

import inspect
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.auth import OwnerPrincipal, require_dashboard_auth
import app.api.routes_health as routes_health
from app.config import settings
from app.main import create_app
from app.storage.repositories import SignalRepository


def test_owner_routes_require_authentication() -> None:
    client = TestClient(create_app())

    for path in (
        "/",
        "/signals/latest",
        "/blocks/active",
        "/api/v1/owner/snapshot",
    ):
        assert client.get(path).status_code == 401


def test_owner_routes_fail_closed_when_auth_configuration_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dashboard_basic_auth_user", None)
    monkeypatch.setattr(settings, "dashboard_basic_auth_password", None)
    client = TestClient(create_app())

    for path in (
        "/",
        "/signals/latest",
        "/blocks/active",
        "/api/v1/owner/snapshot",
    ):
        assert client.get(path).status_code == 503


def test_role_header_cannot_escalate_server_mapped_viewer(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dashboard_basic_auth_role", "owner_viewer")
    probe = FastAPI()

    @probe.get("/principal")
    async def principal(
        owner: OwnerPrincipal = Depends(require_dashboard_auth),
    ) -> dict[str, str]:
        return {"username": owner.username, "role": owner.role}

    response = TestClient(probe).get(
        "/principal",
        auth=("owner", "secret"),
        headers={"X-Owner-Role": "OWNER_ADMIN"},
    )

    assert response.status_code == 200
    assert response.json() == {"username": "owner", "role": "OWNER_VIEWER"}


def test_invalid_owner_role_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dashboard_basic_auth_role", "unknown_role")

    assert TestClient(create_app()).get("/").status_code == 503


def test_production_ui_has_no_legacy_replay_controls_or_handler() -> None:
    template = Path("app/dashboard/templates/index.html").read_text(encoding="utf-8")
    javascript = Path("app/dashboard/static/app.js").read_text(encoding="utf-8")

    assert 'id="replay-form"' not in template
    assert 'id="replay-logs"' not in template
    assert 'id="replay-result"' not in template
    assert "DISABLED_PENDING_DURABLE_ISOLATED_REPLAY_PR02" in template
    assert "fetch('/replay/logs'" not in javascript
    assert "Replay form handler" not in javascript


def test_signal_series_getters_do_not_rebuild_read_models() -> None:
    for method in (
        SignalRepository.get_signal_series,
        SignalRepository.get_signal_series_detail,
    ):
        assert "refresh_pressure_series" not in inspect.getsource(method)


def test_liveness_is_public_and_declares_stable_identity() -> None:
    response = TestClient(create_app()).get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "live"
    assert response.json()["observer_mode"] == "OBSERVE_ONLY"


def test_readiness_passes_only_required_measured_checks(monkeypatch) -> None:
    async def database_ready() -> dict:
        return {"status": "PASS", "reason_code": "DATABASE_AND_SCHEMA_READY"}

    async def owner_read_models_ready() -> dict:
        return {"status": "PASS", "reason_code": "OWNER_READ_MODEL_ACTIVE"}

    monkeypatch.setattr(routes_health, "_database_readiness", database_ready)
    monkeypatch.setattr(
        routes_health,
        "_owner_read_model_readiness",
        owner_read_models_ready,
    )
    response = TestClient(create_app()).get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["canonical_feed"]["status"] == "UNKNOWN"
    assert payload["checks"]["broker_state"]["status"] == "NOT_MEASURED"


def test_readiness_fails_when_owner_auth_is_missing(monkeypatch) -> None:
    async def database_ready() -> dict:
        return {"status": "PASS", "reason_code": "DATABASE_AND_SCHEMA_READY"}

    async def owner_read_models_ready() -> dict:
        return {"status": "PASS", "reason_code": "OWNER_READ_MODEL_ACTIVE"}

    monkeypatch.setattr(routes_health, "_database_readiness", database_ready)
    monkeypatch.setattr(
        routes_health,
        "_owner_read_model_readiness",
        owner_read_models_ready,
    )
    monkeypatch.setattr(settings, "dashboard_basic_auth_user", None)
    monkeypatch.setattr(settings, "dashboard_basic_auth_password", None)
    response = TestClient(create_app()).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["owner_auth"]["status"] == "FAIL"


def test_readiness_fails_when_database_is_unavailable(monkeypatch) -> None:
    async def database_unavailable() -> dict:
        return {"status": "FAIL", "reason_code": "DATABASE_UNAVAILABLE"}

    async def owner_read_models_unavailable() -> dict:
        return {"status": "FAIL", "reason_code": "OWNER_READ_MODEL_UNAVAILABLE"}

    monkeypatch.setattr(routes_health, "_database_readiness", database_unavailable)
    monkeypatch.setattr(
        routes_health,
        "_owner_read_model_readiness",
        owner_read_models_unavailable,
    )
    client = TestClient(create_app())
    live_response = client.get("/health/live")
    response = client.get("/health/ready")

    assert live_response.status_code == 200
    assert response.status_code == 503
    assert response.json()["checks"]["database"]["status"] == "FAIL"


def test_readiness_fails_closed_when_owner_generation_is_not_active(monkeypatch) -> None:
    async def database_ready() -> dict:
        return {"status": "PASS", "reason_code": "DATABASE_AND_SCHEMA_READY"}

    async def owner_read_models_missing() -> dict:
        return {"status": "FAIL", "reason_code": "OWNER_READ_MODEL_NOT_ACTIVE"}

    monkeypatch.setattr(routes_health, "_database_readiness", database_ready)
    monkeypatch.setattr(
        routes_health,
        "_owner_read_model_readiness",
        owner_read_models_missing,
    )
    response = TestClient(create_app()).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["owner_read_models"] == {
        "status": "FAIL",
        "reason_code": "OWNER_READ_MODEL_NOT_ACTIVE",
    }
