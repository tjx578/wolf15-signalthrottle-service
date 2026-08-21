from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

import app.storage.postgres as postgres
from app.api.routes_health import _database_readiness
from app.config import settings
from app.contracts.observer_telemetry import (
    OBSERVER_TELEMETRY_SCHEMA_VERSION,
    ObserverTelemetryEvent,
    TelemetryIntakeStatus,
)
from app.services.telemetry_intake import TelemetryIntakeService
from app.storage.consumer_cursors import ConsumerCursorRepository
from app.storage.migrations import (
    _migration_014_observer_durable_foundation,
    _migration_015_observer_durable_reducer_recovery,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def _event(**overrides) -> ObserverTelemetryEvent:
    values = {
        "event_id": uuid4(),
        "stream_id": "legacy:USDJPY",
        "stream_sequence": 1,
        "event_type": "SIGNAL_THROTTLE",
        "source_authority": "LEGACY_OBSERVATIONAL",
        "schema_version": OBSERVER_TELEMETRY_SCHEMA_VERSION,
        "occurred_at_utc": datetime(2026, 8, 21, 8, 0, tzinfo=UTC),
        "payload": {"symbol": "USDJPY", "count": 3},
    }
    values.update(overrides)
    return ObserverTelemetryEvent(**values)


def _legacy_schema_checksum(database_url: str) -> tuple:
    with psycopg.connect(database_url, autocommit=True) as conn:
        rows = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'signalthrottle' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        ).fetchall()
        result = []
        for (table_name,) in rows:
            query = sql.SQL(
                """
                SELECT COUNT(*)::BIGINT,
                       MD5(COALESCE(STRING_AGG(row_hash, '' ORDER BY row_hash), ''))
                FROM (
                    SELECT MD5(TO_JSONB(t)::TEXT) AS row_hash
                    FROM {}.{} AS t
                ) AS checksummed_rows
                """
            ).format(sql.Identifier("signalthrottle"), sql.Identifier(table_name))
            result.append((table_name, *conn.execute(query).fetchone()))
        return tuple(result)


async def _prepare_database(database_url: str) -> None:
    await postgres.close_db()
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS observer_plane CASCADE")
        conn.execute(Path("app/storage/schema.sql").read_text(encoding="utf-8"))
    await _migration_014_observer_durable_foundation()
    await _migration_015_observer_durable_reducer_recovery()


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="OPTIONAL_EXTERNAL_INTEGRATION: TEST_DATABASE_URL is not configured",
)
def test_atomic_intake_conflicts_concurrency_cursor_and_restart(monkeypatch) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "database_pool_min_size", 1)
    monkeypatch.setattr(settings, "database_pool_max_size", 5)

    async def exercise() -> None:
        await _prepare_database(TEST_DATABASE_URL)
        service = TelemetryIntakeService()
        legacy_before = _legacy_schema_checksum(TEST_DATABASE_URL)

        first = _event()
        accepted = await service.ingest(first)
        duplicate = await service.ingest(first)
        assert accepted.status == TelemetryIntakeStatus.ACCEPTED
        assert duplicate.status == TelemetryIntakeStatus.IDEMPOTENT_DUPLICATE

        hash_conflict = first.model_copy(
            update={"payload": {"symbol": "USDJPY", "count": 99}}
        )
        assert (await service.ingest(hash_conflict)).status == (
            TelemetryIntakeStatus.EVENT_ID_HASH_CONFLICT
        )

        sequence_conflict = _event(event_id=uuid4(), payload={"symbol": "EURUSD"})
        assert (await service.ingest(sequence_conflict)).status == (
            TelemetryIntakeStatus.STREAM_SEQUENCE_CONFLICT
        )

        bad_previous = _event(
            event_id=uuid4(),
            stream_sequence=2,
            previous_event_hash="f" * 64,
        )
        assert (await service.ingest(bad_previous)).status == (
            TelemetryIntakeStatus.PREVIOUS_HASH_MISMATCH
        )

        assert (await service.ingest(_event(
            event_id=uuid4(), stream_id="authority", stream_sequence=None,
            source_authority="CLIENT_ADMIN",
        ))).status == TelemetryIntakeStatus.UNKNOWN_SOURCE_AUTHORITY
        assert (await service.ingest(_event(
            event_id=uuid4(), stream_id="schema", stream_sequence=None,
            schema_version="observer.telemetry.v999",
        ))).status == TelemetryIntakeStatus.INVALID_SCHEMA_VERSION

        atomic_failure = _event(
            event_id=uuid4(),
            stream_id="atomic",
            stream_sequence=1,
        )

        async def fail_job(*args, **kwargs):
            raise RuntimeError("injected reducer job failure")

        original_insert = service._jobs.insert_pending
        service._jobs.insert_pending = fail_job
        with pytest.raises(RuntimeError, match="injected reducer job failure"):
            await service.ingest(atomic_failure)
        service._jobs.insert_pending = original_insert

        concurrent = _event(
            event_id=uuid4(),
            stream_id="concurrent-id",
            stream_sequence=1,
        )
        same_event_results = await asyncio.gather(
            service.ingest(concurrent),
            service.ingest(concurrent),
        )
        assert {result.status for result in same_event_results} == {
            TelemetryIntakeStatus.ACCEPTED,
            TelemetryIntakeStatus.IDEMPOTENT_DUPLICATE,
        }

        sequence_a = _event(
            event_id=uuid4(),
            stream_id="concurrent-sequence",
            stream_sequence=1,
            payload={"candidate": "a"},
        )
        sequence_b = _event(
            event_id=uuid4(),
            stream_id="concurrent-sequence",
            stream_sequence=1,
            payload={"candidate": "b"},
        )
        sequence_results = await asyncio.gather(
            service.ingest(sequence_a),
            service.ingest(sequence_b),
        )
        assert {result.status for result in sequence_results} == {
            TelemetryIntakeStatus.ACCEPTED,
            TelemetryIntakeStatus.STREAM_SEQUENCE_CONFLICT,
        }

        winning_event = next(
            event
            for event, result in zip(
                (sequence_a, sequence_b), sequence_results, strict=True
            )
            if result.status == TelemetryIntakeStatus.ACCEPTED
        )
        cursor_repository = ConsumerCursorRepository()
        assert await cursor_repository.advance(
            consumer_name="pressure-reducer",
            stream_id=winning_event.stream_id,
            committed_sequence=3,
            committed_event_id=winning_event.event_id,
            committed_payload_hash=winning_event.calculate_payload_hash(),
        )
        assert not await cursor_repository.advance(
            consumer_name="pressure-reducer",
            stream_id=winning_event.stream_id,
            committed_sequence=2,
            committed_event_id=winning_event.event_id,
            committed_payload_hash=winning_event.calculate_payload_hash(),
        )

        async with postgres.get_connection() as conn:
            counts = {}
            for table_name in (
                "telemetry_events", "reducer_jobs", "quarantine_events"
            ):
                cursor = await conn.execute(
                    sql.SQL("SELECT COUNT(*) AS count FROM {}.{}").format(
                        sql.Identifier("observer_plane"),
                        sql.Identifier(table_name),
                    )
                )
                counts[table_name] = (await cursor.fetchone())["count"]
            cursor = await conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM observer_plane.telemetry_events
                WHERE event_id = %s
                """,
                (atomic_failure.event_id,),
            )
            assert (await cursor.fetchone())["count"] == 0
            cursor = await conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM observer_plane.telemetry_events AS event
                LEFT JOIN observer_plane.reducer_jobs AS job
                  ON job.event_id = event.event_id
                WHERE job.event_id IS NULL
                """
            )
            assert (await cursor.fetchone())["count"] == 0
            cursor = await conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM observer_plane.reducer_jobs AS job
                LEFT JOIN observer_plane.telemetry_events AS event
                  ON event.event_id = job.event_id
                WHERE event.event_id IS NULL
                """
            )
            assert (await cursor.fetchone())["count"] == 0
            cursor = await conn.execute(
                """
                SELECT committed_sequence
                FROM observer_plane.consumer_cursors
                WHERE consumer_name = 'pressure-reducer'
                  AND stream_id = %s
                """,
                (winning_event.stream_id,),
            )
            assert (await cursor.fetchone())["committed_sequence"] == 3

        assert counts == {
            "telemetry_events": 3,
            "reducer_jobs": 3,
            "quarantine_events": 6,
        }
        assert _legacy_schema_checksum(TEST_DATABASE_URL) == legacy_before

        readiness = await _database_readiness()
        assert readiness["status"] == "PASS"
        assert readiness["migration_current"] is True

        ledger_counts_before_restart = counts.copy()
        await postgres.close_db()
        duplicate_after_restart = await service.ingest(first)
        assert duplicate_after_restart.status == TelemetryIntakeStatus.IDEMPOTENT_DUPLICATE
        async with postgres.get_connection() as conn:
            for table_name, expected_count in ledger_counts_before_restart.items():
                cursor = await conn.execute(
                    sql.SQL("SELECT COUNT(*) AS count FROM {}.{}").format(
                        sql.Identifier("observer_plane"),
                        sql.Identifier(table_name),
                    )
                )
                assert (await cursor.fetchone())["count"] == expected_count

        async with postgres.get_connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    DELETE FROM observer_plane.schema_revisions
                    WHERE revision_id = '20260821_01_observer_durable_foundation'
                    """
                )
        stale = await _database_readiness()
        assert stale["status"] == "FAIL"
        assert stale["reason_code"] == "OBSERVER_SCHEMA_OUT_OF_SYNC"
        await _migration_014_observer_durable_foundation()
        assert (await _database_readiness())["status"] == "PASS"
        await postgres.close_db()

    asyncio.run(exercise())
