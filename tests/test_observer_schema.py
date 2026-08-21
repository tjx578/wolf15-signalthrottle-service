from __future__ import annotations

from app.storage.observer_schema import (
    OBSERVER_DURABLE_FOUNDATION_DOWN_SQL,
    OBSERVER_DURABLE_FOUNDATION_REVISION,
    OBSERVER_DURABLE_FOUNDATION_UP_SQL,
    OBSERVER_DURABLE_TABLES,
    OBSERVER_SCHEMA,
)


def test_observer_schema_contract_is_isolated_and_complete() -> None:
    assert OBSERVER_SCHEMA == "observer_plane"
    assert OBSERVER_DURABLE_FOUNDATION_REVISION == (
        "20260821_01_observer_durable_foundation"
    )
    assert OBSERVER_DURABLE_TABLES == {
        "telemetry_events",
        "reducer_jobs",
        "consumer_cursors",
        "quarantine_events",
        "read_model_versions",
    }
    for table_name in OBSERVER_DURABLE_TABLES:
        assert f"observer_plane.{table_name}" in OBSERVER_DURABLE_FOUNDATION_UP_SQL


def test_observer_schema_enforces_authority_atomicity_and_append_only_contracts() -> None:
    migration = OBSERVER_DURABLE_FOUNDATION_UP_SQL

    assert "LEGACY_OBSERVATIONAL" in migration
    assert "UNKNOWN" in migration
    assert "CANONICAL_RAW" not in migration
    assert "CANONICAL_DECISION" not in migration
    assert "REFERENCES observer_plane.telemetry_events(event_id)" in migration
    assert "UNIQUE (event_id, reducer_name, reducer_version)" in migration
    assert "UNIQUE (stream_id, stream_sequence)" in migration
    assert "telemetry_events_append_only" in migration
    assert "BEFORE UPDATE OR DELETE" in migration
    assert "pg_advisory_xact_lock" in migration


def test_observer_schema_downgrade_is_scoped_to_observer_plane() -> None:
    assert "signalthrottle." not in OBSERVER_DURABLE_FOUNDATION_DOWN_SQL
    assert "public." not in OBSERVER_DURABLE_FOUNDATION_DOWN_SQL
    assert "DROP SCHEMA IF EXISTS observer_plane" in OBSERVER_DURABLE_FOUNDATION_DOWN_SQL
