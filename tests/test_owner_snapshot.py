from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.routes_owner import get_owner_snapshot_service
from app.contracts.reducer import calculate_output_hash
from app.main import create_app
from app.services.owner_read_models import (
    ARTIFACT_VERSIONS,
    OwnerReadModelSource,
    build_owner_artifact_contents,
)
from app.services.owner_snapshot import OwnerSnapshotService


GENERATION_ID = UUID("20000000-0000-0000-0000-000000000001")


def _active_bundle():
    source = OwnerReadModelSource(
        events=(),
        cursors=(),
        jobs=(),
        quarantines=(),
        rejected_generations=0,
        latest_containment_verification=datetime(2026, 8, 22, 8, 0, tzinfo=UTC),
    )
    contents = build_owner_artifact_contents(source)
    artifact_rows = tuple(
        {
            "generation_id": GENERATION_ID,
            "artifact_name": name,
            "artifact_version": ARTIFACT_VERSIONS[name],
            "source_watermark_hash": source.source_watermark_hash,
            "content_hash": calculate_output_hash(contents[name]),
            "content": contents[name],
        }
        for name in sorted(contents)
    )
    manifest = {
        "read_model": "owner-system-v1",
        "source_watermark": source.source_watermark_hash,
        "reducer_versions": dict(sorted(ARTIFACT_VERSIONS.items())),
        "artifacts": {
            row["artifact_name"]: row["content_hash"] for row in artifact_rows
        },
    }
    generation = {
        "generation_id": GENERATION_ID,
        "source_watermark_hash": source.source_watermark_hash,
        "source_event_id": None,
        "source_end_sequence": None,
        "reducer_versions": ARTIFACT_VERSIONS,
        "output_hash": calculate_output_hash(manifest),
        "created_at": datetime(2026, 8, 22, 8, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 8, 22, 8, 1, tzinfo=UTC),
        "validated_at": datetime(2026, 8, 22, 8, 1, tzinfo=UTC),
    }
    return generation, artifact_rows


class _FakeGenerations:
    def __init__(self, bundle=None) -> None:
        self.bundle = bundle

    async def get_active_bundle(self):
        return self.bundle


def _service(bundle=None) -> OwnerSnapshotService:
    service = OwnerSnapshotService()
    service._generations = _FakeGenerations(bundle)
    return service


def test_owner_snapshot_contract_is_deterministic_and_keeps_unknowns_explicit() -> None:
    service = _service(_active_bundle())
    first = asyncio.run(service.build_snapshot())
    second = asyncio.run(service.build_snapshot())

    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_content_hash == second.snapshot_content_hash
    assert first.source.source_watermark == _active_bundle()[0][
        "source_watermark_hash"
    ]
    assert first.canonical_feed.status == "HOLD_UPSTREAM_TYPED_EXPORT"
    assert first.canonical_feed.freshness == "UNKNOWN"
    assert first.broker_state.status == "NOT_MEASURED"
    assert first.observer.authority == "OBSERVATIONAL_ONLY"


def test_owner_get_routes_share_generation_watermark_and_are_authenticated() -> None:
    app = create_app()
    app.dependency_overrides[get_owner_snapshot_service] = lambda: _service(
        _active_bundle()
    )
    client = TestClient(app)
    paths = (
        "/api/v1/owner/snapshot",
        "/api/v1/owner/stream-health",
        "/api/v1/owner/pairs",
        "/api/v1/owner/incidents",
    )

    assert all(client.get(path).status_code == 401 for path in paths)
    responses = [client.get(path, auth=("owner", "secret")) for path in paths]
    assert all(response.status_code == 200 for response in responses)
    snapshot = responses[0].json()
    artifacts = [response.json() for response in responses[1:]]
    assert {artifact["read_model_generation"] for artifact in artifacts} == {
        snapshot["read_models"]["generation_id"]
    }
    assert {artifact["source_watermark"] for artifact in artifacts} == {
        snapshot["source"]["source_watermark"]
    }


def test_owner_routes_fail_closed_without_active_generation_and_expose_no_mutation() -> None:
    app = create_app()
    app.dependency_overrides[get_owner_snapshot_service] = lambda: _service(None)
    client = TestClient(app)

    response = client.get("/api/v1/owner/snapshot", auth=("owner", "secret"))
    assert response.status_code == 503
    assert response.json()["detail"]["reason_code"] == "OWNER_READ_MODEL_NOT_ACTIVE"
    assert client.post(
        "/api/v1/owner/snapshot", auth=("owner", "secret")
    ).status_code == 405
    for path in (
        "/api/v1/owner/replay",
        "/api/v1/owner/rebuild",
        "/api/v1/owner/maintenance",
    ):
        assert client.post(path, auth=("owner", "secret")).status_code == 404
