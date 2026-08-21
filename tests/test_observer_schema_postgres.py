from __future__ import annotations

import asyncio
import os

import psycopg
import pytest

import app.storage.postgres as postgres
from app.config import settings
from app.storage.migrations import (
    _migration_014_observer_durable_foundation,
    downgrade_observer_durable_foundation,
    get_observer_schema_status,
)
from app.storage.observer_schema import (
    OBSERVER_DURABLE_FOUNDATION_REVISION,
    OBSERVER_DURABLE_TABLES,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="OPTIONAL_EXTERNAL_INTEGRATION: TEST_DATABASE_URL is not configured",
)
def test_observer_migration_upgrade_append_only_and_downgrade(monkeypatch) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)

    async def exercise_migration() -> None:
        try:
            await downgrade_observer_durable_foundation()
            await asyncio.gather(
                _migration_014_observer_durable_foundation(),
                _migration_014_observer_durable_foundation(),
            )
            status = await get_observer_schema_status()
            assert status == {
                "schema": "observer_plane",
                "expected_revision": OBSERVER_DURABLE_FOUNDATION_REVISION,
                "revision_current": True,
                "missing_tables": [],
                "status": "ok",
            }
        finally:
            await postgres.close_db()

    asyncio.run(exercise_migration())

    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'observer_plane'
                  AND table_type = 'BASE TABLE'
                """
            ).fetchall()
        }
        assert OBSERVER_DURABLE_TABLES <= tables

        event_id = "21f1b658-a869-4f01-9852-14827cc4721f"
        conn.execute(
            """
            INSERT INTO observer_plane.telemetry_events (
                event_id, stream_id, stream_sequence, event_type,
                source_authority, schema_version, occurred_at_utc,
                payload_hash, payload
            ) VALUES (
                %s, 'legacy:USDJPY', 1, 'SIGNAL_THROTTLE',
                'LEGACY_OBSERVATIONAL', 'observer.telemetry.v1', NOW(),
                %s, '{}'::jsonb
            )
            """,
            (event_id, "a" * 64),
        )
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            conn.execute(
                """
                UPDATE observer_plane.telemetry_events
                SET payload = '{"mutated": true}'::jsonb
                WHERE event_id = %s
                """,
                (event_id,),
            )

    async def exercise_downgrade() -> None:
        try:
            await downgrade_observer_durable_foundation()
        finally:
            await postgres.close_db()

    asyncio.run(exercise_downgrade())
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        schema_exists = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'observer_plane')"
        ).fetchone()[0]
    assert schema_exists is False

    asyncio.run(exercise_migration())
