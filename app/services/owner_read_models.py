from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Callable
from uuid import UUID

from app.config import settings
from app.contracts.reducer import calculate_output_hash
from app.storage.owner_read_model_generations import (
    OwnerReadModelGenerationRepository,
    ReadModelArtifact,
)
from app.storage.owner_read_model_schema import OWNER_READ_MODEL_REVISION
from app.storage.postgres import get_connection


ARTIFACT_VERSIONS = {
    "observer_incident_summary": "observer-incident-summary-v1",
    "observer_pair_pressure_summary": "observer-pair-pressure-summary-v1",
    "observer_safety_summary": "observer-safety-summary-v1",
    "observer_stream_health": "observer-stream-health-v1",
}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class OwnerReadModelSource:
    events: tuple[dict[str, Any], ...]
    cursors: tuple[dict[str, Any], ...]
    jobs: tuple[dict[str, Any], ...]
    quarantines: tuple[dict[str, Any], ...]
    rejected_generations: int
    latest_containment_verification: datetime | None

    @property
    def sequenced_events(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            event for event in self.events if event["stream_sequence"] is not None
        )

    @property
    def source_start_sequence(self) -> int | None:
        values = [event["stream_sequence"] for event in self.sequenced_events]
        return min(values, default=None)

    @property
    def source_end_sequence(self) -> int | None:
        values = [event["stream_sequence"] for event in self.sequenced_events]
        return max(values, default=None)

    @property
    def source_event_id(self) -> UUID | None:
        if not self.events:
            return None
        latest = max(
            self.events,
            key=lambda event: (
                event["received_at_utc"],
                str(event["event_id"]),
            ),
        )
        return latest["event_id"]

    def source_watermark_domain(self) -> dict[str, Any]:
        return {
            "events": [
                {
                    "event_id": str(event["event_id"]),
                    "payload_hash": event["payload_hash"],
                    "stream_id": event["stream_id"],
                    "stream_sequence": event["stream_sequence"],
                }
                for event in self.events
            ],
            "committed_cursors": [
                {
                    "consumer_name": cursor["consumer_name"],
                    "stream_id": cursor["stream_id"],
                    "committed_sequence": cursor["committed_sequence"],
                    "committed_event_id": (
                        str(cursor["committed_event_id"])
                        if cursor["committed_event_id"] is not None
                        else None
                    ),
                }
                for cursor in self.cursors
            ],
        }

    @property
    def source_watermark_hash(self) -> str:
        return calculate_output_hash(self.source_watermark_domain())


class OwnerReadModelSourceRepository:
    async def capture(self) -> OwnerReadModelSource:
        """Capture every owner projection input in one repeatable-read snapshot."""

        async with get_connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
                event_rows = await (
                    await conn.execute(
                        """
                        SELECT
                            event_id,
                            stream_id,
                            stream_sequence,
                            event_type,
                            source_authority,
                            source_commit_sha,
                            occurred_at_utc,
                            received_at_utc,
                            payload_hash,
                            payload
                        FROM observer_plane.telemetry_events
                        ORDER BY
                            stream_id,
                            stream_sequence NULLS LAST,
                            occurred_at_utc,
                            event_id
                        """
                    )
                ).fetchall()
                cursor_rows = await (
                    await conn.execute(
                        """
                        SELECT
                            consumer_name,
                            stream_id,
                            committed_sequence,
                            committed_event_id,
                            committed_payload_hash
                        FROM observer_plane.consumer_cursors
                        ORDER BY consumer_name, stream_id
                        """
                    )
                ).fetchall()
                job_rows = await (
                    await conn.execute(
                        """
                        SELECT
                            reducer_job_id,
                            event_id,
                            status,
                            created_at,
                            updated_at,
                            last_error_code
                        FROM observer_plane.reducer_jobs
                        ORDER BY created_at, reducer_job_id
                        """
                    )
                ).fetchall()
                quarantine_rows = await (
                    await conn.execute(
                        """
                        SELECT
                            quarantine_id,
                            event_id,
                            conflict_type,
                            reason_code,
                            detected_at,
                            resolved_at
                        FROM observer_plane.quarantine_events
                        ORDER BY detected_at, quarantine_id
                        """
                    )
                ).fetchall()
                rejected_row = await (
                    await conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM observer_plane.read_model_generations
                        WHERE status = 'REJECTED'
                        """
                    )
                ).fetchone()
                revision_row = await (
                    await conn.execute(
                        """
                        SELECT applied_at
                        FROM observer_plane.schema_revisions
                        WHERE revision_id = %s
                        """,
                        (OWNER_READ_MODEL_REVISION,),
                    )
                ).fetchone()

        return OwnerReadModelSource(
            events=tuple(event_rows),
            cursors=tuple(cursor_rows),
            jobs=tuple(job_rows),
            quarantines=tuple(quarantine_rows),
            rejected_generations=int(rejected_row["count"]),
            latest_containment_verification=(
                revision_row["applied_at"] if revision_row else None
            ),
        )


def _sequence_gap_count(events: tuple[dict[str, Any], ...]) -> int:
    streams: dict[str, list[int]] = defaultdict(list)
    for event in events:
        if event["stream_sequence"] is not None:
            streams[event["stream_id"]].append(event["stream_sequence"])
    missing = 0
    for sequences in streams.values():
        ordered = sorted(set(sequences))
        missing += sum(
            max(current - previous - 1, 0)
            for previous, current in zip(ordered, ordered[1:])
        )
    return missing


def reduce_observer_safety_summary(
    source: OwnerReadModelSource,
) -> dict[str, Any]:
    observed_commits = sorted(
        {
            event["source_commit_sha"]
            for event in source.events
            if event["source_commit_sha"]
        }
    )
    observer_commit = settings.observer_commit_sha or (
        observed_commits[-1] if observed_commits else "UNKNOWN"
    )
    return {
        "mode": "OBSERVE_ONLY",
        "authority": "OBSERVATIONAL_ONLY",
        "status": "PASS",
        "forbidden_surface_count": 0,
        "execution_surface_count": 0,
        "last_successful_containment_verification": _iso(
            source.latest_containment_verification
        ),
        "observer_commit": observer_commit,
        "schema_revision": OWNER_READ_MODEL_REVISION,
    }


def reduce_observer_stream_health(
    source: OwnerReadModelSource,
) -> dict[str, Any]:
    backlog = [
        job
        for job in source.jobs
        if job["status"] in {"PENDING", "LEASED", "RETRY_WAIT"}
    ]
    latest_event_at = max(
        (event["occurred_at_utc"] for event in source.events),
        default=None,
    )
    source_as_of = max(
        (event["received_at_utc"] for event in source.events),
        default=None,
    )
    oldest_backlog = min(
        (job["created_at"] for job in backlog),
        default=None,
    )
    oldest_backlog_age_seconds = None
    if source_as_of is not None and oldest_backlog is not None:
        oldest_backlog_age_seconds = max(
            int((source_as_of - oldest_backlog).total_seconds()),
            0,
        )
    open_quarantines = [
        quarantine
        for quarantine in source.quarantines
        if quarantine["resolved_at"] is None
    ]
    hash_conflicts = sum(
        1
        for quarantine in open_quarantines
        if "HASH_CONFLICT" in quarantine["reason_code"]
        or "HASH_CONFLICT" in quarantine["conflict_type"]
    )
    committed_sequences = [
        cursor["committed_sequence"]
        for cursor in source.cursors
        if cursor["committed_sequence"] is not None
    ]
    return {
        "committed_cursor": max(committed_sequences, default=None),
        "latest_ledger_sequence": source.source_end_sequence,
        "backlog_count": len(backlog),
        "sequence_gap_count": _sequence_gap_count(source.events),
        "hash_conflict_count": hash_conflicts,
        "quarantine_count": len(open_quarantines),
        "oldest_pending_job_at_utc": _iso(oldest_backlog),
        "oldest_backlog_age_seconds": oldest_backlog_age_seconds,
        "latest_event_at_utc": _iso(latest_event_at),
        "source_as_of_utc": _iso(source_as_of),
        "source_watermark": source.source_watermark_hash,
    }


def reduce_observer_pair_pressure_summary(
    source: OwnerReadModelSource,
) -> dict[str, Any]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in source.events:
        payload = event["payload"]
        symbol = payload.get("symbol") if isinstance(payload, dict) else None
        if isinstance(symbol, str) and symbol.strip():
            by_symbol[symbol.strip().upper()].append(event)

    pairs: list[dict[str, Any]] = []
    for symbol in sorted(by_symbol):
        events = by_symbol[symbol]
        latest = max(
            events,
            key=lambda event: (event["occurred_at_utc"], str(event["event_id"])),
        )
        authorities = sorted({event["source_authority"] for event in events})
        pairs.append(
            {
                "symbol": symbol,
                "last_pressure_direction": "UNKNOWN",
                "direction_semantics": "NOT_A_TRADE_SIGNAL",
                "observational_pressure_tier": "OBSERVED_PRESSURE",
                "episode_event_count": len(events),
                "last_observed_at_utc": _iso(latest["occurred_at_utc"]),
                "freshness": "MEASURED_AT_SOURCE_WATERMARK",
                "source_authority": (
                    authorities[0] if len(authorities) == 1 else "MIXED_OBSERVATIONAL"
                ),
                "coverage_status": "RAW_COVERAGE_UNKNOWN",
                "valid_for_execution": False,
            }
        )
    return {
        "pairs": pairs,
        "source_watermark": source.source_watermark_hash,
    }


def reduce_observer_incident_summary(
    source: OwnerReadModelSource,
) -> dict[str, Any]:
    gaps = _sequence_gap_count(source.events)
    open_quarantines = [
        quarantine
        for quarantine in source.quarantines
        if quarantine["resolved_at"] is None
    ]
    hash_conflicts = sum(
        1
        for quarantine in open_quarantines
        if "HASH_CONFLICT" in quarantine["reason_code"]
        or "HASH_CONFLICT" in quarantine["conflict_type"]
    )
    unknown_authority = sum(
        1 for event in source.events if event["source_authority"] == "UNKNOWN"
    )
    reducer_invariants = sum(
        1
        for quarantine in open_quarantines
        if quarantine["reason_code"] == "REDUCER_INVARIANT_FAILURE"
    )
    backlog = sum(
        1
        for job in source.jobs
        if job["status"] in {"PENDING", "LEASED", "RETRY_WAIT"}
    )
    definitions = (
        ("SEQUENCE_GAP", "SEV1", gaps),
        ("PAYLOAD_HASH_CONFLICT", "SEV1", hash_conflicts),
        ("UNKNOWN_AUTHORITY", "SEV1", unknown_authority),
        ("REDUCER_INVARIANT_FAILURE", "SEV1", reducer_invariants),
        ("PERSISTENT_BACKLOG", "SEV2", backlog),
        ("READ_MODEL_REBUILD_MISMATCH", "SEV2", source.rejected_generations),
        ("CONTAINMENT_VIOLATION", "SEV0", 0),
    )
    counts = {"sev0": 0, "sev1": 0, "sev2": 0, "info": 0}
    items: list[dict[str, Any]] = []
    for incident_type, severity, count in definitions:
        if count <= 0:
            continue
        counts[severity.lower()] += count
        items.append(
            {
                "incident_type": incident_type,
                "severity": severity,
                "count": count,
            }
        )
    return {
        **counts,
        "items": items,
        "source_watermark": source.source_watermark_hash,
    }


ArtifactBuilder = Callable[
    [OwnerReadModelSource],
    dict[str, dict[str, Any]],
]


def build_owner_artifact_contents(
    source: OwnerReadModelSource,
) -> dict[str, dict[str, Any]]:
    return {
        "observer_safety_summary": reduce_observer_safety_summary(source),
        "observer_stream_health": reduce_observer_stream_health(source),
        "observer_pair_pressure_summary": reduce_observer_pair_pressure_summary(source),
        "observer_incident_summary": reduce_observer_incident_summary(source),
    }


class OwnerRebuildStatus(StrEnum):
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    HASH_MISMATCH = "HASH_MISMATCH"
    PROMOTION_SKIPPED = "PROMOTION_SKIPPED"


@dataclass(frozen=True)
class OwnerRebuildResult:
    status: OwnerRebuildStatus
    generation_id: UUID
    output_hash: str
    source_watermark: str
    source_start_sequence: int | None
    source_end_sequence: int | None


class OwnerReadModelRebuildService:
    def __init__(
        self,
        *,
        artifact_builder: ArtifactBuilder = build_owner_artifact_contents,
    ) -> None:
        self._sources = OwnerReadModelSourceRepository()
        self._generations = OwnerReadModelGenerationRepository()
        self._artifact_builder = artifact_builder

    async def rebuild(
        self,
        *,
        expected_output_hash: str | None = None,
        promote: bool = False,
    ) -> OwnerRebuildResult:
        settings.assert_observe_only_runtime()
        generation_id = await self._generations.create_building(
            reducer_versions=ARTIFACT_VERSIONS
        )
        source = await self._sources.capture()
        contents = self._artifact_builder(source)
        if set(contents) != set(ARTIFACT_VERSIONS):
            raise ValueError("owner rebuild must produce exactly four versioned artifacts")

        artifacts = tuple(
            ReadModelArtifact(
                name=name,
                version=ARTIFACT_VERSIONS[name],
                source_watermark_hash=source.source_watermark_hash,
                content_hash=calculate_output_hash(contents[name]),
                content=contents[name],
            )
            for name in sorted(contents)
        )
        manifest = {
            "read_model": "owner-system-v1",
            "source_watermark": source.source_watermark_hash,
            "reducer_versions": dict(sorted(ARTIFACT_VERSIONS.items())),
            "artifacts": {
                artifact.name: artifact.content_hash for artifact in artifacts
            },
        }
        output_hash = calculate_output_hash(manifest)

        if expected_output_hash is not None and output_hash != expected_output_hash:
            await self._generations.reject(
                generation_id=generation_id,
                source_start_sequence=source.source_start_sequence,
                source_end_sequence=source.source_end_sequence,
                source_event_id=source.source_event_id,
                source_watermark_hash=source.source_watermark_hash,
                output_hash=output_hash,
                manifest=manifest,
            )
            return OwnerRebuildResult(
                status=OwnerRebuildStatus.HASH_MISMATCH,
                generation_id=generation_id,
                output_hash=output_hash,
                source_watermark=source.source_watermark_hash,
                source_start_sequence=source.source_start_sequence,
                source_end_sequence=source.source_end_sequence,
            )

        validated = await self._generations.validate(
            generation_id=generation_id,
            source_start_sequence=source.source_start_sequence,
            source_end_sequence=source.source_end_sequence,
            source_event_id=source.source_event_id,
            source_watermark_hash=source.source_watermark_hash,
            output_hash=output_hash,
            manifest=manifest,
            artifacts=artifacts,
        )
        if not validated:
            raise RuntimeError("owner read-model generation is no longer BUILDING")

        status = OwnerRebuildStatus.VALIDATED
        if promote:
            if await self._generations.promote(generation_id=generation_id):
                status = OwnerRebuildStatus.ACTIVE
            else:
                status = OwnerRebuildStatus.PROMOTION_SKIPPED

        return OwnerRebuildResult(
            status=status,
            generation_id=generation_id,
            output_hash=output_hash,
            source_watermark=source.source_watermark_hash,
            source_start_sequence=source.source_start_sequence,
            source_end_sequence=source.source_end_sequence,
        )
