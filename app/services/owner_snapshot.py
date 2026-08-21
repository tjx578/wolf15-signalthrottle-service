from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.config import settings
from app.contracts.owner_snapshot import (
    OwnerBrokerStateV1,
    OwnerCanonicalFeedStateV1,
    OwnerCapabilitiesV1,
    OwnerContainmentStateV1,
    OwnerDataQualityStateV1,
    OwnerIncidentCountsV1,
    OwnerObserverIdentityV1,
    OwnerReadModelResponseV1,
    OwnerReadModelStateV1,
    OwnerSourceStateV1,
    OwnerSystemSnapshotV1,
)
from app.contracts.reducer import calculate_output_hash
from app.services.owner_read_models import ARTIFACT_VERSIONS
from app.storage.owner_read_model_generations import (
    OwnerReadModelGenerationRepository,
)


class OwnerSnapshotUnavailable(RuntimeError):
    pass


class OwnerSnapshotInvariantFailure(RuntimeError):
    pass


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class OwnerSnapshotService:
    def __init__(self) -> None:
        self._generations = OwnerReadModelGenerationRepository()

    async def _load(
        self,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], UUID, datetime]:
        bundle = await self._generations.get_active_bundle()
        if bundle is None:
            raise OwnerSnapshotUnavailable("no active owner read-model generation")
        generation, rows = bundle
        if {row["artifact_name"] for row in rows} != set(ARTIFACT_VERSIONS):
            raise OwnerSnapshotInvariantFailure(
                "active owner generation does not contain exactly four artifacts"
            )
        if any(
            row["source_watermark_hash"] != generation["source_watermark_hash"]
            for row in rows
        ):
            raise OwnerSnapshotInvariantFailure("mixed artifact watermarks detected")
        for row in rows:
            if calculate_output_hash(row["content"]) != row["content_hash"]:
                raise OwnerSnapshotInvariantFailure("artifact content hash mismatch")

        artifacts = {row["artifact_name"]: row for row in rows}
        manifest = {
            "read_model": "owner-system-v1",
            "source_watermark": generation["source_watermark_hash"],
            "reducer_versions": dict(sorted(generation["reducer_versions"].items())),
            "artifacts": {
                name: artifacts[name]["content_hash"] for name in sorted(artifacts)
            },
        }
        if calculate_output_hash(manifest) != generation["output_hash"]:
            raise OwnerSnapshotInvariantFailure("generation manifest hash mismatch")

        as_of = generation["validated_at"] or generation["completed_at"]
        if as_of is None:
            raise OwnerSnapshotInvariantFailure("active generation has no as-of time")
        as_of = _as_utc(as_of)
        snapshot_id = uuid5(
            NAMESPACE_URL,
            f"wolf15-owner-snapshot:{generation['generation_id']}:{generation['output_hash']}",
        )
        return generation, artifacts, snapshot_id, as_of

    async def build_snapshot(self) -> OwnerSystemSnapshotV1:
        generation, artifacts, snapshot_id, as_of = await self._load()
        safety = artifacts["observer_safety_summary"]["content"]
        stream = artifacts["observer_stream_health"]["content"]
        incidents = artifacts["observer_incident_summary"]["content"]

        latest_event_at = stream.get("latest_event_at_utc")
        ledger_freshness_seconds = None
        if latest_event_at:
            parsed = datetime.fromisoformat(latest_event_at.replace("Z", "+00:00"))
            ledger_freshness_seconds = max(
                int((as_of - _as_utc(parsed)).total_seconds()),
                0,
            )

        quality_values = (
            int(stream["sequence_gap_count"]),
            int(stream["hash_conflict_count"]),
            int(stream["quarantine_count"]),
            int(stream["backlog_count"]),
        )
        quality_status = "DEGRADED" if any(quality_values) else "PASS"
        capabilities = OwnerCapabilitiesV1()
        content_hash_domain = {
            "source_watermark": generation["source_watermark_hash"],
            "active_generation": str(generation["generation_id"]),
            "read_model_hashes": {
                name: row["content_hash"] for name, row in sorted(artifacts.items())
            },
            "containment": {
                "status": safety["status"],
                "phase2_surface_count": safety["phase2_surface_count"],
                "execution_surface_count": safety["execution_surface_count"],
                "forbidden_artifact_count": safety["forbidden_artifact_count"],
            },
            "incident_counters": {
                key: int(incidents[key]) for key in ("sev0", "sev1", "sev2", "info")
            },
            "stream_health": stream,
            "capabilities": capabilities.model_dump(mode="json"),
        }
        snapshot_content_hash = calculate_output_hash(content_hash_domain)

        return OwnerSystemSnapshotV1(
            snapshot_id=snapshot_id,
            snapshot_content_hash=snapshot_content_hash,
            created_at_utc=_as_utc(generation["created_at"]),
            as_of_utc=as_of,
            observer=OwnerObserverIdentityV1(
                commit_sha=safety["observer_commit"],
                deployment_environment=settings.deployment_environment.upper(),
            ),
            source=OwnerSourceStateV1(
                committed_stream_sequence=stream["committed_cursor"],
                committed_event_id=(
                    UUID(stream["committed_event_id"])
                    if stream["committed_event_id"]
                    else None
                ),
                source_watermark=generation["source_watermark_hash"],
                ledger_freshness_seconds=ledger_freshness_seconds,
            ),
            read_models=OwnerReadModelStateV1(
                generation_id=generation["generation_id"],
                reducer_versions=generation["reducer_versions"],
                generated_at_utc=as_of,
                output_hash=generation["output_hash"],
            ),
            containment=OwnerContainmentStateV1(
                status=safety["status"],
                phase2_surface_count=safety["phase2_surface_count"],
                execution_surface_count=safety["execution_surface_count"],
                forbidden_artifact_count=safety["forbidden_artifact_count"],
            ),
            data_quality=OwnerDataQualityStateV1(
                status=quality_status,
                sequence_gap_count=quality_values[0],
                hash_conflict_count=quality_values[1],
                quarantine_count=quality_values[2],
                backlog_count=quality_values[3],
                oldest_backlog_age_seconds=stream["oldest_backlog_age_seconds"],
            ),
            canonical_feed=OwnerCanonicalFeedStateV1(),
            broker_state=OwnerBrokerStateV1(),
            incidents=OwnerIncidentCountsV1(
                **{
                    key: int(incidents[key])
                    for key in ("sev0", "sev1", "sev2", "info")
                }
            ),
            capabilities=capabilities,
        )

    async def get_artifact(self, artifact_name: str) -> OwnerReadModelResponseV1:
        generation, artifacts, snapshot_id, as_of = await self._load()
        if artifact_name not in artifacts:
            raise OwnerSnapshotInvariantFailure(
                f"active generation is missing artifact {artifact_name}"
            )
        artifact = artifacts[artifact_name]
        return OwnerReadModelResponseV1(
            snapshot_id=snapshot_id,
            source_watermark=generation["source_watermark_hash"],
            read_model_generation=generation["generation_id"],
            as_of_utc=as_of,
            artifact_name=artifact_name,
            artifact_version=artifact["artifact_version"],
            artifact_content_hash=artifact["content_hash"],
            data=artifact["content"],
        )
