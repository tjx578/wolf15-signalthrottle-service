from __future__ import annotations

from app.storage.observer_reducer_schema import (
    OBSERVER_REDUCER_JOB_COLUMNS,
    OBSERVER_REDUCER_QUARANTINE_COLUMNS,
    OBSERVER_REDUCER_RECOVERY_DOWN_SQL,
    OBSERVER_REDUCER_RECOVERY_REVISION,
    OBSERVER_REDUCER_RECOVERY_TABLES,
    OBSERVER_REDUCER_RECOVERY_UP_SQL,
)


def test_reducer_recovery_schema_contract_is_additive_and_worker_safe() -> None:
    assert OBSERVER_REDUCER_RECOVERY_REVISION == (
        "20260822_02_durable_reducer_recovery"
    )
    assert OBSERVER_REDUCER_RECOVERY_TABLES == {
        "reducer_outputs",
        "read_model_generations",
        "read_model_current_generations",
    }
    assert OBSERVER_REDUCER_JOB_COLUMNS == {
        "lease_token",
        "leased_at",
        "completed_at",
        "output_hash",
        "retry_policy_version",
    }
    assert OBSERVER_REDUCER_QUARANTINE_COLUMNS == {
        "reducer_job_id",
        "reducer_name",
        "reducer_version",
        "attempt_count",
        "retry_policy_version",
        "error_detail",
    }
    for table_name in OBSERVER_REDUCER_RECOVERY_TABLES:
        assert f"observer_plane.{table_name}" in OBSERVER_REDUCER_RECOVERY_UP_SQL


def test_reducer_recovery_schema_has_required_states_and_generation_pointer() -> None:
    migration = OBSERVER_REDUCER_RECOVERY_UP_SQL

    for status in ("PENDING", "LEASED", "DONE", "RETRY_WAIT", "QUARANTINED"):
        assert status in migration
    assert "lease_token" in migration
    assert "lease_expires_at > leased_at" in migration
    assert "uq_observer_reducer_logical_output" in migration
    assert "read_model_current_generations" in migration
    assert "DELETE live" not in migration
    assert "signalthrottle." not in migration


def test_reducer_recovery_downgrade_does_not_drop_observer_foundation() -> None:
    downgrade = OBSERVER_REDUCER_RECOVERY_DOWN_SQL

    assert "DROP SCHEMA" not in downgrade
    assert "DROP TABLE IF EXISTS observer_plane.reducer_outputs" in downgrade
    assert "DROP TABLE IF EXISTS observer_plane.telemetry_events" not in downgrade
    assert "signalthrottle." not in downgrade
