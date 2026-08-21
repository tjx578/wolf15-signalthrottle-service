from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.contracts.reducer import calculate_output_hash
from app.services.owner_read_models import (
    ARTIFACT_VERSIONS,
    OwnerReadModelSource,
    build_owner_artifact_contents,
)
from app.storage.owner_read_model_schema import (
    OWNER_READ_MODEL_DOWN_SQL,
    OWNER_READ_MODEL_NAME,
    OWNER_READ_MODEL_REVISION,
    OWNER_READ_MODEL_UP_SQL,
)


def _source() -> OwnerReadModelSource:
    return OwnerReadModelSource(
        events=(
            {
                "event_id": UUID("00000000-0000-0000-0000-000000000001"),
                "stream_id": "legacy:USDJPY",
                "stream_sequence": 1,
                "event_type": "SIGNAL_THROTTLE",
                "source_authority": "LEGACY_OBSERVATIONAL",
                "source_commit_sha": None,
                "occurred_at_utc": datetime(2026, 8, 22, 8, 0, tzinfo=UTC),
                "received_at_utc": datetime(2026, 8, 22, 8, 0, 1, tzinfo=UTC),
                "payload_hash": "a" * 64,
                "payload": {"symbol": "USDJPY", "direction": "BUY"},
            },
            {
                "event_id": UUID("00000000-0000-0000-0000-000000000003"),
                "stream_id": "legacy:USDJPY",
                "stream_sequence": 3,
                "event_type": "SIGNAL_THROTTLE",
                "source_authority": "LEGACY_OBSERVATIONAL",
                "source_commit_sha": None,
                "occurred_at_utc": datetime(2026, 8, 22, 8, 1, tzinfo=UTC),
                "received_at_utc": datetime(2026, 8, 22, 8, 1, 1, tzinfo=UTC),
                "payload_hash": "b" * 64,
                "payload": {"symbol": "USDJPY", "direction": "SELL"},
            },
        ),
        cursors=(
            {
                "consumer_name": "owner-test",
                "stream_id": "legacy:USDJPY",
                "committed_sequence": 1,
                "committed_event_id": UUID(
                    "00000000-0000-0000-0000-000000000001"
                ),
                "committed_payload_hash": "a" * 64,
            },
        ),
        jobs=(
            {
                "reducer_job_id": UUID(
                    "10000000-0000-0000-0000-000000000001"
                ),
                "event_id": UUID("00000000-0000-0000-0000-000000000003"),
                "status": "PENDING",
                "created_at": datetime(2026, 8, 22, 8, 0, 30, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 22, 8, 0, 30, tzinfo=UTC),
                "last_error_code": None,
            },
        ),
        quarantines=(),
        rejected_generations=0,
        latest_containment_verification=datetime(
            2026, 8, 22, 7, 59, tzinfo=UTC
        ),
    )


def test_owner_artifacts_are_deterministic_and_share_one_watermark() -> None:
    source = _source()
    first = build_owner_artifact_contents(source)
    second = build_owner_artifact_contents(source)

    assert set(first) == set(ARTIFACT_VERSIONS)
    assert calculate_output_hash(first) == calculate_output_hash(second)
    assert {
        artifact.get("source_watermark")
        for artifact in first.values()
        if "source_watermark" in artifact
    } == {source.source_watermark_hash}


def test_pair_pressure_never_promotes_payload_direction_to_trade_signal() -> None:
    pairs = build_owner_artifact_contents(_source())[
        "observer_pair_pressure_summary"
    ]["pairs"]

    assert pairs == [
        {
            "symbol": "USDJPY",
            "last_pressure_direction": "UNKNOWN",
            "direction_semantics": "NOT_A_TRADE_SIGNAL",
            "observational_pressure_tier": "OBSERVED_PRESSURE",
            "episode_event_count": 2,
            "last_observed_at_utc": "2026-08-22T08:01:00Z",
            "freshness": "MEASURED_AT_SOURCE_WATERMARK",
            "source_authority": "LEGACY_OBSERVATIONAL",
            "coverage_status": "RAW_COVERAGE_UNKNOWN",
            "valid_for_execution": False,
        }
    ]


def test_stream_and_incident_models_preserve_gap_and_backlog_degradation() -> None:
    artifacts = build_owner_artifact_contents(_source())
    stream = artifacts["observer_stream_health"]
    incidents = artifacts["observer_incident_summary"]

    assert stream["committed_cursor"] == 1
    assert stream["latest_ledger_sequence"] == 3
    assert stream["sequence_gap_count"] == 1
    assert stream["backlog_count"] == 1
    assert incidents["sev1"] == 1
    assert incidents["sev2"] == 1


def test_owner_generation_schema_enforces_atomic_active_generation() -> None:
    assert OWNER_READ_MODEL_REVISION in OWNER_READ_MODEL_UP_SQL
    assert OWNER_READ_MODEL_NAME in OWNER_READ_MODEL_UP_SQL
    assert "WHERE status = 'ACTIVE'" in OWNER_READ_MODEL_UP_SQL
    assert "read_model_artifacts" in OWNER_READ_MODEL_UP_SQL
    assert "observer_incidents" in OWNER_READ_MODEL_UP_SQL
    assert "DROP TABLE IF EXISTS observer_plane.read_model_artifacts" in (
        OWNER_READ_MODEL_DOWN_SQL
    )
