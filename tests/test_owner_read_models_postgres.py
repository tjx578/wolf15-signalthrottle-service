from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

import app.storage.postgres as postgres
from app.config import settings
from app.contracts.observer_telemetry import (
    OBSERVER_TELEMETRY_SCHEMA_VERSION,
    ObserverTelemetryEvent,
)
from app.services.owner_read_models import (
    OwnerReadModelRebuildService,
    OwnerRebuildStatus,
)
from app.services.telemetry_intake import TelemetryIntakeService
from app.storage.migrations import (
    _migration_014_observer_durable_foundation,
    _migration_015_observer_durable_reducer_recovery,
    _migration_016_owner_snapshot_read_models,
    get_owner_read_model_schema_status,
)
from app.storage.owner_read_model_generations import (
    OwnerReadModelGenerationRepository,
)
from app.storage.owner_read_model_schema import OWNER_READ_MODEL_NAME


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def _event(stream_id: str, sequence: int) -> ObserverTelemetryEvent:
    return ObserverTelemetryEvent(
        event_id=uuid4(),
        stream_id=stream_id,
        stream_sequence=sequence,
        event_type="SIGNAL_THROTTLE",
        source_authority="LEGACY_OBSERVATIONAL",
        schema_version=OBSERVER_TELEMETRY_SCHEMA_VERSION,
        occurred_at_utc=datetime(2026, 8, 22, 8, sequence, tzinfo=UTC),
        payload={"symbol": "USDJPY", "count": sequence},
    )


async def _prepare_database(database_url: str) -> None:
    """Bootstrap only; CI supplies a disposable PostgreSQL database."""

    await postgres.close_db()
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(Path("app/storage/schema.sql").read_text(encoding="utf-8"))
    await _migration_014_observer_durable_foundation()
    await _migration_015_observer_durable_reducer_recovery()
    await asyncio.gather(
        _migration_016_owner_snapshot_read_models(),
        _migration_016_owner_snapshot_read_models(),
    )


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="OPTIONAL_EXTERNAL_INTEGRATION: TEST_DATABASE_URL is not configured",
)
def test_owner_generation_promotion_is_deterministic_atomic_and_fenced(
    monkeypatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "database_pool_min_size", 1)
    monkeypatch.setattr(settings, "database_pool_max_size", 8)

    async def exercise() -> None:
        await _prepare_database(TEST_DATABASE_URL)
        assert (await get_owner_read_model_schema_status())["status"] == "ok"
        stream_id = f"owner-read-model-test:{uuid4()}"
        intake = TelemetryIntakeService()
        for sequence in (1, 2):
            await intake.ingest(_event(stream_id, sequence))

        rebuild = OwnerReadModelRebuildService()
        first = await rebuild.rebuild(promote=True)
        assert first.status == OwnerRebuildStatus.ACTIVE
        assert await rebuild._generations.count_active() == 1

        repeated = await rebuild.rebuild(
            expected_output_hash=first.output_hash,
            promote=True,
        )
        assert repeated.output_hash == first.output_hash
        assert repeated.status == OwnerRebuildStatus.PROMOTION_SKIPPED
        assert await rebuild._generations.count_active() == 1

        await intake.ingest(_event(stream_id, 3))
        concurrent = await asyncio.gather(
            OwnerReadModelRebuildService().rebuild(promote=True),
            OwnerReadModelRebuildService().rebuild(promote=True),
        )
        assert {result.status for result in concurrent} == {
            OwnerRebuildStatus.ACTIVE,
            OwnerRebuildStatus.PROMOTION_SKIPPED,
        }
        assert concurrent[0].output_hash == concurrent[1].output_hash
        assert await rebuild._generations.count_active() == 1

        bundle = await OwnerReadModelGenerationRepository().get_active_bundle()
        assert bundle is not None
        generation, artifacts = bundle
        assert generation["status"] == "ACTIVE"
        assert len(artifacts) == 4
        assert {artifact["source_watermark_hash"] for artifact in artifacts} == {
            generation["source_watermark_hash"]
        }
        assert {artifact["generation_id"] for artifact in artifacts} == {
            generation["generation_id"]
        }

        active_before_mismatch = generation["generation_id"]
        mismatch = await rebuild.rebuild(
            expected_output_hash="0" * 64,
            promote=True,
        )
        assert mismatch.status == OwnerRebuildStatus.HASH_MISMATCH
        active_after = await rebuild._generations.get_active_bundle()
        assert active_after is not None
        assert active_after[0]["generation_id"] == active_before_mismatch

        async with postgres.get_connection() as conn:
            invariant = await (
                await conn.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active,
                        COUNT(*) FILTER (WHERE status = 'REJECTED') AS rejected
                    FROM observer_plane.read_model_generations
                    WHERE read_model_name = %s
                    """,
                    (OWNER_READ_MODEL_NAME,),
                )
            ).fetchone()
        assert invariant == {"active": 1, "rejected": 1}
        await postgres.close_db()

    asyncio.run(exercise())
