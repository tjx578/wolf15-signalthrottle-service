from __future__ import annotations


OBSERVER_SCHEMA = "observer_plane"
OBSERVER_DURABLE_FOUNDATION_REVISION = "20260821_01_observer_durable_foundation"
OBSERVER_DURABLE_TABLES = frozenset(
    {
        "telemetry_events",
        "reducer_jobs",
        "consumer_cursors",
        "quarantine_events",
        "read_model_versions",
    }
)


OBSERVER_DURABLE_FOUNDATION_UP_SQL = f"""
SELECT pg_advisory_xact_lock(
    hashtext('wolf15-signalthrottle-service:{OBSERVER_DURABLE_FOUNDATION_REVISION}')
);

CREATE SCHEMA IF NOT EXISTS {OBSERVER_SCHEMA};

CREATE TABLE IF NOT EXISTS {OBSERVER_SCHEMA}.schema_revisions (
    revision_id TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS {OBSERVER_SCHEMA}.telemetry_events (
    event_id UUID PRIMARY KEY,
    stream_id TEXT NOT NULL CHECK (BTRIM(stream_id) <> ''),
    stream_sequence BIGINT CHECK (stream_sequence IS NULL OR stream_sequence >= 0),
    previous_event_hash CHAR(64),
    event_type TEXT NOT NULL CHECK (BTRIM(event_type) <> ''),
    source_authority TEXT NOT NULL,
    source_provenance TEXT,
    source_commit_sha TEXT,
    schema_version TEXT NOT NULL CHECK (BTRIM(schema_version) <> ''),
    policy_version TEXT,
    occurred_at_utc TIMESTAMPTZ NOT NULL,
    received_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload_hash CHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_observer_stream_sequence UNIQUE (stream_id, stream_sequence),
    CONSTRAINT ck_observer_source_authority
        CHECK (source_authority IN ('LEGACY_OBSERVATIONAL', 'UNKNOWN')),
    CONSTRAINT ck_observer_previous_event_hash
        CHECK (
            previous_event_hash IS NULL
            OR previous_event_hash ~ '^[0-9a-f]{{64}}$'
        ),
    CONSTRAINT ck_observer_payload_hash
        CHECK (payload_hash ~ '^[0-9a-f]{{64}}$')
);

CREATE INDEX IF NOT EXISTS idx_observer_telemetry_stream_time
    ON {OBSERVER_SCHEMA}.telemetry_events (stream_id, occurred_at_utc, event_id);
CREATE INDEX IF NOT EXISTS idx_observer_telemetry_received
    ON {OBSERVER_SCHEMA}.telemetry_events (received_at_utc, event_id);

CREATE TABLE IF NOT EXISTS {OBSERVER_SCHEMA}.reducer_jobs (
    reducer_job_id UUID PRIMARY KEY,
    event_id UUID NOT NULL
        REFERENCES {OBSERVER_SCHEMA}.telemetry_events(event_id),
    reducer_name TEXT NOT NULL CHECK (BTRIM(reducer_name) <> ''),
    reducer_version TEXT NOT NULL CHECK (BTRIM(reducer_version) <> ''),
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ,
    last_error_code TEXT,
    last_error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_observer_event_reducer
        UNIQUE (event_id, reducer_name, reducer_version),
    CONSTRAINT ck_observer_reducer_status
        CHECK (status IN ('PENDING', 'LEASED', 'DONE', 'FAILED', 'QUARANTINED'))
);

CREATE INDEX IF NOT EXISTS idx_observer_reducer_claim
    ON {OBSERVER_SCHEMA}.reducer_jobs (status, next_attempt_at, created_at);

CREATE TABLE IF NOT EXISTS {OBSERVER_SCHEMA}.consumer_cursors (
    consumer_name TEXT NOT NULL CHECK (BTRIM(consumer_name) <> ''),
    stream_id TEXT NOT NULL CHECK (BTRIM(stream_id) <> ''),
    committed_sequence BIGINT CHECK (
        committed_sequence IS NULL OR committed_sequence >= 0
    ),
    committed_event_id UUID,
    committed_payload_hash CHAR(64),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, stream_id),
    CONSTRAINT ck_observer_cursor_payload_hash
        CHECK (
            committed_payload_hash IS NULL
            OR committed_payload_hash ~ '^[0-9a-f]{{64}}$'
        )
);

CREATE TABLE IF NOT EXISTS {OBSERVER_SCHEMA}.quarantine_events (
    quarantine_id UUID PRIMARY KEY,
    event_id UUID,
    stream_id TEXT,
    stream_sequence BIGINT,
    conflict_type TEXT NOT NULL,
    existing_payload_hash CHAR(64),
    received_payload_hash CHAR(64),
    received_payload JSONB,
    reason_code TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolution_note TEXT,
    CONSTRAINT ck_observer_quarantine_conflict_type
        CHECK (
            conflict_type IN (
                'EVENT_ID_HASH_CONFLICT',
                'STREAM_SEQUENCE_CONFLICT',
                'PREVIOUS_HASH_MISMATCH',
                'INVALID_SCHEMA_VERSION',
                'UNKNOWN_SOURCE_AUTHORITY'
            )
        ),
    CONSTRAINT ck_observer_quarantine_reason_code
        CHECK (
            reason_code IN (
                'EVENT_ID_HASH_CONFLICT',
                'STREAM_SEQUENCE_CONFLICT',
                'PREVIOUS_HASH_MISMATCH',
                'INVALID_SCHEMA_VERSION',
                'UNKNOWN_SOURCE_AUTHORITY'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_observer_quarantine_detected
    ON {OBSERVER_SCHEMA}.quarantine_events (detected_at, quarantine_id);
CREATE INDEX IF NOT EXISTS idx_observer_quarantine_event
    ON {OBSERVER_SCHEMA}.quarantine_events (event_id);

CREATE TABLE IF NOT EXISTS {OBSERVER_SCHEMA}.read_model_versions (
    read_model_name TEXT PRIMARY KEY CHECK (BTRIM(read_model_name) <> ''),
    reducer_version TEXT NOT NULL CHECK (BTRIM(reducer_version) <> ''),
    source_watermark BIGINT,
    source_event_id UUID,
    output_hash CHAR(64),
    rebuilt_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_observer_read_model_output_hash
        CHECK (output_hash IS NULL OR output_hash ~ '^[0-9a-f]{{64}}$')
);

CREATE OR REPLACE FUNCTION {OBSERVER_SCHEMA}.reject_telemetry_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'observer telemetry ledger is append-only'
        USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS telemetry_events_append_only
    ON {OBSERVER_SCHEMA}.telemetry_events;
CREATE TRIGGER telemetry_events_append_only
    BEFORE UPDATE OR DELETE ON {OBSERVER_SCHEMA}.telemetry_events
    FOR EACH ROW EXECUTE FUNCTION {OBSERVER_SCHEMA}.reject_telemetry_mutation();

INSERT INTO {OBSERVER_SCHEMA}.schema_revisions (revision_id)
VALUES ('{OBSERVER_DURABLE_FOUNDATION_REVISION}')
ON CONFLICT (revision_id) DO NOTHING;
"""


OBSERVER_DURABLE_FOUNDATION_DOWN_SQL = f"""
SELECT pg_advisory_xact_lock(
    hashtext('wolf15-signalthrottle-service:{OBSERVER_DURABLE_FOUNDATION_REVISION}')
);
DROP SCHEMA IF EXISTS {OBSERVER_SCHEMA} CASCADE;
"""
