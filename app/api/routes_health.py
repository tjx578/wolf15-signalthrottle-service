from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.storage.migrations import (
    get_observer_schema_status,
    get_pressure_blocks_schema_status,
)
from app.storage.postgres import get_cursor, get_pool_stats

logger = logging.getLogger(__name__)
router = APIRouter()


def _runtime_identity() -> dict[str, Any]:
    return {
        "service": settings.service_name,
        "deployment_environment": settings.deployment_environment.upper(),
        "observer_mode": settings.observer_mode.upper(),
        "observer_authority": settings.observer_authority.upper(),
        "containment_profile": "PHASE1_OBSERVE_ONLY",
        "execution_allowed": False,
    }


@router.get("/health")
@router.get("/health/live")
async def health_live() -> dict[str, Any]:
    return {
        "status": "live",
        **_runtime_identity(),
    }


async def _database_readiness() -> dict[str, Any]:
    if not settings.database_url:
        return {
            "status": "FAIL",
            "reason_code": "DATABASE_URL_NOT_CONFIGURED",
        }

    try:
        async with get_cursor() as cur:
            await cur.execute("SELECT 1 AS ready")
            row = await cur.fetchone()
        if not row or row.get("ready") != 1:
            return {
                "status": "FAIL",
                "reason_code": "DATABASE_PROBE_INVALID_RESPONSE",
            }

        schema = await get_pressure_blocks_schema_status()
        if schema.get("status") != "ok":
            return {
                "status": "FAIL",
                "reason_code": "OBSERVER_SCHEMA_OUT_OF_SYNC",
                "missing_columns": schema.get("missing_columns", []),
                "missing_indexes": schema.get("missing_indexes", []),
            }
        observer_schema = await get_observer_schema_status()
        if observer_schema.get("status") != "ok":
            return {
                "status": "FAIL",
                "reason_code": "OBSERVER_SCHEMA_OUT_OF_SYNC",
                "expected_revision": observer_schema.get("expected_revision"),
                "revision_current": observer_schema.get("revision_current", False),
                "missing_tables": observer_schema.get("missing_tables", []),
            }
        return {
            "status": "PASS",
            "reason_code": "DATABASE_POOL_AND_SCHEMAS_READY",
            "pool": get_pool_stats(),
            "observer_schema": "AVAILABLE",
            "migration_revision": observer_schema.get("expected_revision"),
            "migration_current": True,
        }
    except Exception as exc:
        logger.warning("Readiness database probe failed: %s", exc)
        return {
            "status": "FAIL",
            "reason_code": "DATABASE_UNAVAILABLE",
            "error_type": type(exc).__name__,
        }


@router.get("/health/ready")
async def health_ready() -> JSONResponse:
    containment_status = "PASS"
    containment_reason = "OBSERVER_BOUNDARY_VALID"
    try:
        settings.assert_observe_only_runtime()
    except ValueError:
        containment_status = "FAIL"
        containment_reason = "OBSERVER_BOUNDARY_INVALID"

    checks = {
        "containment": {
            "status": containment_status,
            "reason_code": containment_reason,
        },
        "owner_auth": {
            "status": "PASS" if settings.owner_auth_configured() else "FAIL",
            "reason_code": (
                "OWNER_AUTH_CONFIGURED"
                if settings.owner_auth_configured()
                else "OWNER_AUTH_NOT_CONFIGURED"
            ),
        },
        "webhook_auth": {
            "status": "PASS" if settings.webhook_auth_configured() else "FAIL",
            "reason_code": (
                "WEBHOOK_AUTH_CONFIGURED"
                if settings.webhook_auth_configured()
                else "WEBHOOK_AUTH_NOT_CONFIGURED"
            ),
        },
        "database": await _database_readiness(),
        "canonical_feed": {
            "status": "UNKNOWN",
            "reason_code": "HOLD_UPSTREAM_TYPED_EXPORT",
            "required_for_current_observer_readiness": False,
        },
        "broker_state": {
            "status": "NOT_MEASURED",
            "reason_code": "OUTSIDE_OBSERVER_AUTHORITY",
            "required_for_current_observer_readiness": False,
        },
    }
    required_checks = ("containment", "owner_auth", "webhook_auth", "database")
    ready = all(checks[name]["status"] == "PASS" for name in required_checks)
    payload = {
        "status": "ready" if ready else "not_ready",
        **_runtime_identity(),
        "checks": checks,
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)
