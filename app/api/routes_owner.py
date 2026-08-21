from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.contracts.owner_snapshot import (
    OwnerReadModelResponseV1,
    OwnerSystemSnapshotV1,
)
from app.services.owner_snapshot import (
    OwnerSnapshotInvariantFailure,
    OwnerSnapshotService,
    OwnerSnapshotUnavailable,
)


router = APIRouter()


def get_owner_snapshot_service() -> OwnerSnapshotService:
    return OwnerSnapshotService()


SnapshotService = Annotated[
    OwnerSnapshotService,
    Depends(get_owner_snapshot_service),
]


def _fail_closed(exc: RuntimeError) -> HTTPException:
    reason = (
        "OWNER_READ_MODEL_NOT_ACTIVE"
        if isinstance(exc, OwnerSnapshotUnavailable)
        else "OWNER_SNAPSHOT_INVARIANT_FAILURE"
    )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"reason_code": reason},
    )


@router.get("/snapshot", response_model=OwnerSystemSnapshotV1)
async def owner_snapshot(service: SnapshotService) -> OwnerSystemSnapshotV1:
    try:
        return await service.build_snapshot()
    except (OwnerSnapshotUnavailable, OwnerSnapshotInvariantFailure) as exc:
        raise _fail_closed(exc) from exc


async def _artifact(
    service: OwnerSnapshotService,
    artifact_name: str,
) -> OwnerReadModelResponseV1:
    try:
        return await service.get_artifact(artifact_name)
    except (OwnerSnapshotUnavailable, OwnerSnapshotInvariantFailure) as exc:
        raise _fail_closed(exc) from exc


@router.get("/stream-health", response_model=OwnerReadModelResponseV1)
async def owner_stream_health(service: SnapshotService) -> OwnerReadModelResponseV1:
    return await _artifact(service, "observer_stream_health")


@router.get("/pairs", response_model=OwnerReadModelResponseV1)
async def owner_pairs(service: SnapshotService) -> OwnerReadModelResponseV1:
    return await _artifact(service, "observer_pair_pressure_summary")


@router.get("/incidents", response_model=OwnerReadModelResponseV1)
async def owner_incidents(service: SnapshotService) -> OwnerReadModelResponseV1:
    return await _artifact(service, "observer_incident_summary")
