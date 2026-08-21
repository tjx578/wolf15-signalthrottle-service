from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

import app.storage.postgres as postgres
from app.config import settings
from app.contracts.observer_telemetry import (
    OBSERVER_TELEMETRY_SCHEMA_VERSION,
    ObserverTelemetryEvent,
    TelemetryIntakeStatus,
)
from app.contracts.reducer import (
    ReducerErrorCode,
    ReducerFailure,
    RetryPolicy,
    calculate_output_hash,
    reduce_observer_event,
)
from app.services.read_model_rebuild import ReadModelRebuildService, RebuildStatus
from app.services.reducer_worker import (
    DurableReducerWorker,
    ReducerRunStatus,
)
from app.services.telemetry_intake import TelemetryIntakeService
from app.storage.migrations import (
    _migration_014_observer_durable_foundation,
    _migration_015_observer_durable_reducer_recovery,
    downgrade_observer_durable_reducer_recovery,
    get_observer_reducer_schema_status,
)
from app.storage.reducer_jobs import ReducerJobRepository


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def _event(**overrides) -> ObserverTelemetryEvent:
    values = {
        "event_id": uuid4(),
        "stream_id": f"legacy:{uuid4()}",
        "stream_sequence": None,
        "event_type": "SIGNAL_THROTTLE",
        "source_authority": "LEGACY_OBSERVATIONAL",
        "schema_version": OBSERVER_TELEMETRY_SCHEMA_VERSION,
        "occurred_at_utc": datetime(2026, 8, 22, 8, 0, tzinfo=UTC),
        "payload": {"symbol": "USDJPY", "count": 3},
    }
    values.update(overrides)
    return ObserverTelemetryEvent(**values)


async def _prepare_database(database_url: str) -> None:
    await postgres.close_db()
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS observer_plane CASCADE")
        conn.execute(Path("app/storage/schema.sql").read_text(encoding="utf-8"))
    await _migration_014_observer_durable_foundation()


async def _set_claim_recoverable(job_id: UUID) -> None:
    async with postgres.get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE observer_plane.reducer_jobs
                SET leased_at = NOW() - INTERVAL '2 minutes',
                    lease_expires_at = NOW() - INTERVAL '1 minute'
                WHERE reducer_job_id = %s
                """,
                (job_id,),
            )


async def _force_retry_due(job_id: UUID) -> None:
    async with postgres.get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE observer_plane.reducer_jobs
                SET next_attempt_at = NOW() - INTERVAL '1 second'
                WHERE reducer_job_id = %s AND status = 'RETRY_WAIT'
                """,
                (job_id,),
            )


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="OPTIONAL_EXTERNAL_INTEGRATION: TEST_DATABASE_URL is not configured",
)
def test_reducer_recovery_migration_is_concurrent_and_reversible(monkeypatch) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)

    async def exercise() -> None:
        await _prepare_database(TEST_DATABASE_URL)
        legacy_event_id = uuid4()
        legacy_job_id = uuid4()
        async with postgres.get_connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO observer_plane.telemetry_events (
                        event_id, stream_id, event_type, source_authority,
                        schema_version, occurred_at_utc, payload_hash, payload
                    ) VALUES (
                        %s, 'pre-pr02b-lease', 'SIGNAL_THROTTLE',
                        'LEGACY_OBSERVATIONAL', 'observer.telemetry.v1', NOW(),
                        %s, '{}'::jsonb
                    )
                    """,
                    (legacy_event_id, "a" * 64),
                )
                await conn.execute(
                    """
                    INSERT INTO observer_plane.reducer_jobs (
                        reducer_job_id, event_id, reducer_name, reducer_version,
                        status, lease_owner, lease_expires_at
                    ) VALUES (
                        %s, %s, 'observer_pressure', 'observer-pressure-v1',
                        'LEASED', 'legacy-worker', NOW() + INTERVAL '5 minutes'
                    )
                    """,
                    (legacy_job_id, legacy_event_id),
                )
        await asyncio.gather(
            _migration_015_observer_durable_reducer_recovery(),
            _migration_015_observer_durable_reducer_recovery(),
        )
        status = await get_observer_reducer_schema_status()
        assert status["status"] == "ok"
        assert status["missing_tables"] == []
        assert status["missing_columns"] == []
        migrated_job = await ReducerJobRepository().get(legacy_job_id)
        assert migrated_job is not None
        assert migrated_job["status"] == "PENDING"
        assert migrated_job["lease_owner"] is None
        assert migrated_job["lease_token"] is None

        await downgrade_observer_durable_reducer_recovery()
        assert (await get_observer_reducer_schema_status())["status"] == (
            "OBSERVER_REDUCER_SCHEMA_OUT_OF_SYNC"
        )
        await _migration_015_observer_durable_reducer_recovery()
        assert (await get_observer_reducer_schema_status())["status"] == "ok"
        await postgres.close_db()

    asyncio.run(exercise())


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="OPTIONAL_EXTERNAL_INTEGRATION: TEST_DATABASE_URL is not configured",
)
def test_leasing_retry_recovery_cursor_concurrency_and_rebuild(monkeypatch) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "database_pool_min_size", 1)
    monkeypatch.setattr(settings, "database_pool_max_size", 12)

    async def exercise() -> None:
        await _prepare_database(TEST_DATABASE_URL)
        await _migration_015_observer_durable_reducer_recovery()
        intake = TelemetryIntakeService()
        jobs = ReducerJobRepository()

        crash_event = _event(stream_id="crash-recovery", stream_sequence=1)
        assert (await intake.ingest(crash_event)).status == TelemetryIntakeStatus.ACCEPTED
        claims = await asyncio.gather(
            jobs.claim_next(
                lease_owner="worker-a",
                lease_duration=timedelta(seconds=30),
            ),
            jobs.claim_next(
                lease_owner="worker-b",
                lease_duration=timedelta(seconds=30),
            ),
        )
        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        abandoned = winners[0]
        assert abandoned.attempt_count == 1

        await _set_claim_recoverable(abandoned.reducer_job_id)
        await postgres.close_db()
        recovered = await jobs.claim_next(
            lease_owner="worker-after-restart",
            lease_duration=timedelta(seconds=30),
        )
        assert recovered is not None
        assert recovered.reducer_job_id == abandoned.reducer_job_id
        assert recovered.attempt_count == 2
        expected_hash = calculate_output_hash(reduce_observer_event(recovered))

        recovery_worker = DurableReducerWorker(lease_owner="recovery-processor")
        recovered_result = await recovery_worker.process_claim(recovered)
        assert recovered_result.status == ReducerRunStatus.DONE
        assert recovered_result.output_hash == expected_hash
        stale_result = await recovery_worker.process_claim(abandoned)
        assert stale_result.status == ReducerRunStatus.STALE_LEASE

        async with postgres.get_connection() as conn:
            row = await (
                await conn.execute(
                    """
                    SELECT
                        COUNT(*) AS outputs,
                        MIN(output_hash) AS output_hash
                    FROM observer_plane.reducer_outputs
                    WHERE reducer_job_id = %s
                    """,
                    (abandoned.reducer_job_id,),
                )
            ).fetchone()
        assert row == {"outputs": 1, "output_hash": expected_hash}

        retry_event = _event(stream_id="durable-retry")
        await intake.ingest(retry_event)
        calls = 0

        def transient_once(claim):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ReducerFailure(
                    ReducerErrorCode.TRANSIENT_DEPENDENCY,
                    "dependency unavailable",
                )
            return reduce_observer_event(claim)

        retry_worker = DurableReducerWorker(
            lease_owner="retry-worker",
            reducer=transient_once,
            retry_policy=RetryPolicy(
                delays=(timedelta(seconds=5), timedelta(seconds=30))
            ),
        )
        retry_wait = await retry_worker.run_once()
        assert retry_wait.status == ReducerRunStatus.RETRY_WAIT
        retry_row = await jobs.get(retry_wait.reducer_job_id)
        assert retry_row is not None
        assert retry_row["status"] == "RETRY_WAIT"
        assert retry_row["attempt_count"] == 1
        assert retry_row["next_attempt_at"] > datetime.now(UTC)
        assert retry_row["last_error_code"] == "TRANSIENT_DEPENDENCY"
        await _force_retry_due(retry_wait.reducer_job_id)
        retried = await retry_worker.run_once()
        assert retried.status == ReducerRunStatus.DONE
        assert retried.attempt_count == 2

        fatal_event = _event(stream_id="fatal-event")
        await intake.ingest(fatal_event)

        def invalid_event(_claim):
            raise ReducerFailure(ReducerErrorCode.INVALID_EVENT, "invalid payload")

        fatal_worker = DurableReducerWorker(
            lease_owner="fatal-worker",
            reducer=invalid_event,
        )
        fatal = await fatal_worker.run_once()
        assert fatal.status == ReducerRunStatus.QUARANTINED
        fatal_row = await jobs.get(fatal.reducer_job_id)
        assert fatal_row is not None
        assert fatal_row["status"] == "QUARANTINED"
        assert fatal_row["attempt_count"] == 1

        chain: list[ObserverTelemetryEvent] = []
        previous_hash = None
        for sequence in range(100, 104):
            event = _event(
                stream_id="contiguous-stream",
                stream_sequence=sequence,
                previous_event_hash=previous_hash,
                payload={"sequence": sequence},
            )
            assert (await intake.ingest(event)).status == TelemetryIntakeStatus.ACCEPTED
            chain.append(event)
            previous_hash = event.calculate_payload_hash()

        chain_claims = []
        for index in range(4):
            claim = await jobs.claim_next(
                lease_owner=f"cursor-worker-{index}",
                lease_duration=timedelta(seconds=30),
            )
            assert claim is not None
            chain_claims.append(claim)
        assert [claim.stream_sequence for claim in chain_claims] == [100, 101, 102, 103]

        cursor_worker = DurableReducerWorker(
            lease_owner="cursor-processor",
            consumer_name="contiguous-cursor",
        )
        await cursor_worker.process_claim(chain_claims[0])
        await cursor_worker.process_claim(chain_claims[1])
        out_of_order = await cursor_worker.process_claim(chain_claims[3])
        assert out_of_order.committed_sequence == 101
        async with postgres.get_connection() as conn:
            cursor_row = await (
                await conn.execute(
                    """
                    SELECT committed_sequence
                    FROM observer_plane.consumer_cursors
                    WHERE consumer_name = 'contiguous-cursor'
                      AND stream_id = 'contiguous-stream'
                    """
                )
            ).fetchone()
        assert cursor_row["committed_sequence"] == 101
        gap_filled = await cursor_worker.process_claim(chain_claims[2])
        assert gap_filled.committed_sequence == 103

        duplicate = _event(stream_id="duplicate", payload={"value": "same"})
        assert (await intake.ingest(duplicate)).status == TelemetryIntakeStatus.ACCEPTED
        assert (await intake.ingest(duplicate)).status == (
            TelemetryIntakeStatus.IDEMPOTENT_DUPLICATE
        )
        conflict = duplicate.model_copy(update={"payload": {"value": "different"}})
        assert (await intake.ingest(conflict)).status == (
            TelemetryIntakeStatus.EVENT_ID_HASH_CONFLICT
        )
        duplicate_result = await DurableReducerWorker(
            lease_owner="duplicate-worker"
        ).run_once()
        assert duplicate_result.status == ReducerRunStatus.DONE

        async with postgres.get_connection() as conn:
            before_row = await (
                await conn.execute(
                    "SELECT COUNT(*) AS count FROM observer_plane.reducer_outputs"
                )
            ).fetchone()
        outputs_before_batch = before_row["count"]

        batch_events = [
            _event(stream_id=f"batch:{index}", payload={"index": index})
            for index in range(100)
        ]
        intake_results = await asyncio.gather(
            *(intake.ingest(event) for event in batch_events)
        )
        assert all(
            result.status == TelemetryIntakeStatus.ACCEPTED
            for result in intake_results
        )

        workers = [
            DurableReducerWorker(lease_owner=f"batch-worker-{index}")
            for index in range(4)
        ]

        async def drain(worker: DurableReducerWorker) -> int:
            completed = 0
            while True:
                result = await worker.run_once()
                if result.status == ReducerRunStatus.IDLE:
                    return completed
                assert result.status == ReducerRunStatus.DONE
                completed += 1

        completed_counts = await asyncio.gather(*(drain(worker) for worker in workers))
        assert sum(completed_counts) == 100
        async with postgres.get_connection() as conn:
            after_row = await (
                await conn.execute(
                    "SELECT COUNT(*) AS count FROM observer_plane.reducer_outputs"
                )
            ).fetchone()
            active_row = await (
                await conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM observer_plane.reducer_jobs
                    WHERE status = 'LEASED'
                    """
                )
            ).fetchone()
        assert after_row["count"] - outputs_before_batch == 100
        assert active_row["count"] == 0

        rebuild = ReadModelRebuildService()
        first_generation = await rebuild.rebuild(
            read_model_name="observer-event-index",
            reducer_version="event-index-v1",
            source_stream_id="contiguous-stream",
            promote=True,
        )
        second_generation = await rebuild.rebuild(
            read_model_name="observer-event-index",
            reducer_version="event-index-v1",
            source_stream_id="contiguous-stream",
            expected_output_hash=first_generation.output_hash,
            promote=True,
        )
        assert first_generation.status == RebuildStatus.CURRENT
        assert second_generation.status == RebuildStatus.CURRENT
        assert first_generation.generation_id != second_generation.generation_id
        assert first_generation.output_hash == second_generation.output_hash
        assert second_generation.source_watermark == 103

        rejected = await rebuild.rebuild(
            read_model_name="observer-event-index",
            reducer_version="event-index-v1",
            source_stream_id="contiguous-stream",
            expected_output_hash="0" * 64,
            promote=True,
        )
        assert rejected.status == RebuildStatus.HASH_MISMATCH
        current = await rebuild._generations.get_current("observer-event-index")
        assert current is not None
        assert current["generation_id"] == second_generation.generation_id
        assert current["status"] == "CURRENT"

        async with postgres.get_connection() as conn:
            invariant_row = await (
                await conn.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (
                            WHERE status = 'LEASED'
                              AND (
                                  lease_owner IS NULL
                                  OR lease_token IS NULL
                                  OR lease_expires_at IS NULL
                              )
                        ) AS invalid_active_leases,
                        COUNT(*) FILTER (WHERE status = 'PENDING') AS pending,
                        COUNT(*) FILTER (WHERE status = 'RETRY_WAIT') AS retry_wait
                    FROM observer_plane.reducer_jobs
                    """
                )
            ).fetchone()
        assert invariant_row == {
            "invalid_active_leases": 0,
            "pending": 0,
            "retry_wait": 0,
        }
        await postgres.close_db()

    asyncio.run(exercise())
