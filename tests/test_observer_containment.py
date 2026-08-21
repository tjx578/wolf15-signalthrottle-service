from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.detector.finalizer as finalizer
import app.lifecycle as lifecycle
import app.main as main
from app.config import Settings


FORBIDDEN_PATHS = {
    "/market/snapshot/{symbol}",
    "/outcomes/summary",
    "/outcomes/backfill",
    "/debug/sync",
    "/debug/schema",
    "/signals/trade-plans",
    "/signals/{signal_id}",
    "/signal-detail/{signal_id}",
    "/replay/logs",
}


def test_production_route_inventory_has_no_phase2_surface() -> None:
    app = main.create_app()
    paths = {route.path for route in app.routes}

    assert not (paths & FORBIDDEN_PATHS)
    assert {"/health", "/webhook/log", "/signals/latest"} <= paths


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phase1_observe_only", False),
        ("observer_mode", "analysis"),
        ("observer_authority", "execution"),
        ("signalthrottle_mode", "phase2"),
        ("enable_market_context", True),
        ("enable_trade_plans", True),
        ("enable_outcome_worker", True),
        ("enable_legacy_replay", True),
        ("execution_allowed", True),
        ("finnhub_api_key", "forbidden-key"),
    ],
)
def test_startup_configuration_rejects_phase2_capability(field: str, value: object) -> None:
    values = {
        "phase1_observe_only": True,
        "signalthrottle_mode": "phase1",
        "enable_market_context": False,
        "enable_trade_plans": False,
        "enable_outcome_worker": False,
        "enable_legacy_replay": False,
        "execution_allowed": False,
        "finnhub_api_key": None,
        field: value,
    }

    with pytest.raises(ValidationError, match="Observer containment violation"):
        Settings(_env_file=None, **values)


def test_phase1_runtime_modules_do_not_import_phase2_components() -> None:
    for module in (main, lifecycle, finalizer):
        source = inspect.getsource(module)
        for forbidden_import in (
            "market_context",
            "OutcomeWorker",
            "routes_market",
            "routes_outcomes",
            "routes_debug",
            "models.trade_plan",
            "scoring.execution_grader",
            "scoring.final_score",
        ):
            assert forbidden_import not in source


def test_production_image_manifest_excludes_phase2_sources() -> None:
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    for forbidden_path in (
        "app/market",
        "app/outcomes",
        "app/planner",
        "app/api/routes_debug.py",
        "app/api/routes_market.py",
        "app/api/routes_outcomes.py",
        "app/api/routes_replay.py",
        "app/models/trade_plan.py",
        "app/scoring/execution_grader.py",
    ):
        assert forbidden_path in dockerignore


def test_health_declares_zero_execution_authority() -> None:
    payload = TestClient(main.create_app()).get("/health").json()

    assert payload["deployment_environment"] == "PRODUCTION"
    assert payload["observer_mode"] == "OBSERVE_ONLY"
    assert payload["observer_authority"] == "OBSERVATIONAL_ONLY"
    assert payload["containment_profile"] == "PHASE1_OBSERVE_ONLY"
    assert payload["execution_allowed"] is False
