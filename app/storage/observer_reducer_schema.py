from __future__ import annotations


OBSERVER_REDUCER_RECOVERY_REVISION = "20260822_02_durable_reducer_recovery"
OBSERVER_REDUCER_RECOVERY_TABLES = frozenset(
    {
        "reducer_outputs",
        "read_model_generations",
        "read_model_current_generations",
    }
)
OBSERVER_REDUCER_JOB_COLUMNS = frozenset(
    {
        "lease_token",
        "leased_at",
        "completed_at",
        "output_hash",
        "retry_policy_version",
    }
)
OBSERVER_REDUCER_QUARANTINE_COLUMNS = frozenset(
    {
        "reducer_job_id",
        "reducer_name",
        "reducer_version",
        "attempt_count",
        "retry_policy_version",
        "error_detail",
    }
)


OBSERVER_REDUCER_RECOVERY_UP_SQL = f"""
SELECT pg_advisory_xact_lock(
    hashtext('wolf15-signalthrottle-service:{OBSERVER_REDUCER_RECOVERY_REVISION}')
);

ALTER TABLE observer_plane.reducer_jobs
    ADD COLUMN IF NOT EXISTS lease_token UUID,
    ADD COLUMN IF NOT EXISTS leased_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS output_hash CHAR(64),
    ADD COLUMN IF NOT EXISTS retry_policy_version TEXT NOT NULL
        DEFAULT 'observer-retry-v1';

UPDATE observer_plane.reducer_jobs
SET status = 'RETRY_WAIT',
    next_attempt_at = COALESCE(next_attempt_at, NOW()),
    updated_at = NOW()
WHERE status = 'FAILED';

UPDATE observer_plane.reducer_jobs
SET status = 'PENDING',
    lease_owner = NULL,
    lease_token = NULL,
    leased_at = NULL,
    lease_expires_at = NULL,
    next_attempt_at = NULL,
    updated_at = NOW()
WHERE status = 'LEASED';

UPDATE observer_plane.reducer_jobs
SET lease_owner = NULL,
    lease_token = NULL,
    leased_at = NULL,
    lease_expires_at = NULL
WHERE status <> 'LEASED';

ALTER TABLE observer_plane.reducer_jobs
    DROP CONSTRAINT IF EXISTS ck_observer_reducer_status,
    DROP CONSTRAINT IF EXISTS ck_observer_reducer_lease_state,
    DROP CONSTRAINT IF EXISTS ck_observer_reducer_retry_state,
    DROP CONSTRAINT IF EXISTS ck_observer_reducer_output_hash;

ALTER TABLE observer_plane.reducer_jobs
    ADD CONSTRAINT ck_observer_reducer_status
        CHECK (
            status IN (
                'PENDING', 'LEASED', 'DONE', 'RETRY_WAIT', 'QUARANTINED'
            )
        ),
    ADD CONSTRAINT ck_observer_reducer_lease_state
        CHECK (
            (
                status = 'LEASED'
                AND lease_owner IS NOT NULL
                AND lease_token IS NOT NULL
                AND leased_at IS NOT NULL
                AND lease_expires_at IS NOT NULL
                AND lease_expires_at > leased_at
            )
            OR
            (
                status <> 'LEASED'
                AND lease_owner IS NULL
                AND lease_token IS NULL
                AND leased_at IS NULL
                AND lease_expires_at IS NULL
            )
        ),
    ADD CONSTRAINT ck_observer_reducer_retry_state
        CHECK (status <> 'RETRY_WAIT' OR next_attempt_at IS NOT NULL),
    ADD CONSTRAINT ck_observer_reducer_output_hash
        CHECK (output_hash IS NULL OR output_hash ~ '^[0-9a-f]{{64}}$');

CREATE INDEX IF NOT EXISTS idx_observer_reducer_lease_claim
    ON observer_plane.reducer_jobs (
        reducer_name,
        reducer_version,
        status,
        next_attempt_at,
        lease_expires_at,
        created_at,
        reducer_job_id
    );

ALTER TABLE observer_plane.quarantine_events
    ADD COLUMN IF NOT EXISTS reducer_job_id UUID
        REFERENCES observer_plane.reducer_jobs(reducer_job_id),
    ADD COLUMN IF NOT EXISTS reducer_name TEXT,
    ADD COLUMN IF NOT EXISTS reducer_version TEXT,
    ADD COLUMN IF NOT EXISTS attempt_count INTEGER,
    ADD COLUMN IF NOT EXISTS retry_policy_version TEXT,
    ADD COLUMN IF NOT EXISTS error_detail TEXT;

ALTER TABLE observer_plane.quarantine_events
    DROP CONSTRAINT IF EXISTS ck_observer_quarantine_conflict_type,
    DROP CONSTRAINT IF EXISTS ck_observer_quarantine_reason_code,
    DROP CONSTRAINT IF EXISTS ck_observer_quarantine_attempt_count,
    DROP CONSTRAINT IF EXISTS uq_observer_reducer_quarantine;

ALTER TABLE observer_plane.quarantine_events
    ADD CONSTRAINT ck_observer_quarantine_conflict_type
        CHECK (
            conflict_type IN (
                'EVENT_ID_HASH_CONFLICT',
                'STREAM_SEQUENCE_CONFLICT',
                'PREVIOUS_HASH_MISMATCH',
                'INVALID_SCHEMA_VERSION',
                'UNKNOWN_SOURCE_AUTHORITY',
                'TRANSIENT_DATABASE',
                'TRANSIENT_DEPENDENCY',
                'INVALID_EVENT',
                'HASH_CONFLICT',
                'REDUCER_INVARIANT_FAILURE',
                'UNKNOWN',
                'RETRY_EXHAUSTED'
            )
        ),
    ADD CONSTRAINT ck_observer_quarantine_reason_code
        CHECK (
            reason_code IN (
                'EVENT_ID_HASH_CONFLICT',
                'STREAM_SEQUENCE_CONFLICT',
                'PREVIOUS_HASH_MISMATCH',
                'INVALID_SCHEMA_VERSION',
                'UNKNOWN_SOURCE_AUTHORITY',
                'TRANSIENT_DATABASE',
                'TRANSIENT_DEPENDENCY',
                'INVALID_EVENT',
                'HASH_CONFLICT',
                'REDUCER_INVARIANT_FAILURE',
                'UNKNOWN',
                'RETRY_EXHAUSTED'
            )
        ),
    ADD CONSTRAINT ck_observer_quarantine_attempt_count
        CHECK (attempt_count IS NULL OR attempt_count >= 1),
    ADD CONSTRAINT uq_observer_reducer_quarantine
        UNIQUE (reducer_job_id);

CREATE TABLE IF NOT EXISTS observer_plane.reducer_outputs (
    reducer_job_id UUID PRIMARY KEY
        REFERENCES observer_plane.reducer_jobs(reducer_job_id),
    event_id UUID NOT NULL
        REFERENCES observer_plane.telemetry_events(event_id),
    reducer_name TEXT NOT NULL CHECK (BTRIM(reducer_name) <> ''),
    reducer_version TEXT NOT NULL CHECK (BTRIM(reducer_version) <> ''),
    input_payload_hash CHAR(64) NOT NULL,
    output_hash CHAR(64) NOT NULL,
    output JSONB NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_observer_reducer_logical_output
        UNIQUE (event_id, reducer_name, reducer_version),
    CONSTRAINT ck_observer_reducer_input_hash
        CHECK (input_payload_hash ~ '^[0-9a-f]{{64}}$'),
    CONSTRAINT ck_observer_reducer_result_hash
        CHECK (output_hash ~ '^[0-9a-f]{{64}}$')
);

CREATE INDEX IF NOT EXISTS idx_observer_reducer_outputs_event
    ON observer_plane.reducer_outputs (event_id, reducer_name, reducer_version);

CREATE TABLE IF NOT EXISTS observer_plane.read_model_generations (
    generation_id UUID PRIMARY KEY,
    read_model_name TEXT NOT NULL CHECK (BTRIM(read_model_name) <> ''),
    reducer_version TEXT NOT NULL CHECK (BTRIM(reducer_version) <> ''),
    status TEXT NOT NULL DEFAULT 'BUILDING',
    source_stream_id TEXT,
    source_watermark BIGINT,
    source_event_id UUID,
    output_hash CHAR(64),
    output JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    promoted_at TIMESTAMPTZ,
    CONSTRAINT ck_observer_generation_status
        CHECK (status IN ('BUILDING', 'READY', 'CURRENT', 'REJECTED')),
    CONSTRAINT ck_observer_generation_hash
        CHECK (output_hash IS NULL OR output_hash ~ '^[0-9a-f]{{64}}$'),
    CONSTRAINT ck_observer_generation_ready
        CHECK (
            status = 'BUILDING'
            OR (output_hash IS NOT NULL AND completed_at IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_observer_generation_lookup
    ON observer_plane.read_model_generations (
        read_model_name, created_at DESC, generation_id
    );

CREATE TABLE IF NOT EXISTS observer_plane.read_model_current_generations (
    read_model_name TEXT PRIMARY KEY CHECK (BTRIM(read_model_name) <> ''),
    generation_id UUID NOT NULL UNIQUE
        REFERENCES observer_plane.read_model_generations(generation_id),
    promoted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO observer_plane.schema_revisions (revision_id)
VALUES ('{OBSERVER_REDUCER_RECOVERY_REVISION}')
ON CONFLICT (revision_id) DO NOTHING;
"""


OBSERVER_REDUCER_RECOVERY_DOWN_SQL = f"""
SELECT pg_advisory_xact_lock(
    hashtext('wolf15-signalthrottle-service:{OBSERVER_REDUCER_RECOVERY_REVISION}')
);

DELETE FROM observer_plane.schema_revisions
WHERE revision_id = '{OBSERVER_REDUCER_RECOVERY_REVISION}';

DROP TABLE IF EXISTS observer_plane.read_model_current_generations;
DROP TABLE IF EXISTS observer_plane.read_model_generations;
DROP TABLE IF EXISTS observer_plane.reducer_outputs;

ALTER TABLE observer_plane.reducer_jobs
    DROP CONSTRAINT IF EXISTS ck_observer_reducer_status,
    DROP CONSTRAINT IF EXISTS ck_observer_reducer_lease_state,
    DROP CONSTRAINT IF EXISTS ck_observer_reducer_retry_state,
    DROP CONSTRAINT IF EXISTS ck_observer_reducer_output_hash;

UPDATE observer_plane.reducer_jobs
SET status = 'FAILED'
WHERE status = 'RETRY_WAIT';

ALTER TABLE observer_plane.reducer_jobs
    ADD CONSTRAINT ck_observer_reducer_status
        CHECK (status IN ('PENDING', 'LEASED', 'DONE', 'FAILED', 'QUARANTINED'));

DROP INDEX IF EXISTS observer_plane.idx_observer_reducer_lease_claim;

ALTER TABLE observer_plane.reducer_jobs
    DROP COLUMN IF EXISTS lease_token,
    DROP COLUMN IF EXISTS leased_at,
    DROP COLUMN IF EXISTS completed_at,
    DROP COLUMN IF EXISTS output_hash,
    DROP COLUMN IF EXISTS retry_policy_version;

ALTER TABLE observer_plane.quarantine_events
    DROP CONSTRAINT IF EXISTS ck_observer_quarantine_conflict_type,
    DROP CONSTRAINT IF EXISTS ck_observer_quarantine_reason_code,
    DROP CONSTRAINT IF EXISTS ck_observer_quarantine_attempt_count,
    DROP CONSTRAINT IF EXISTS uq_observer_reducer_quarantine;

ALTER TABLE observer_plane.quarantine_events
    DROP COLUMN IF EXISTS reducer_job_id,
    DROP COLUMN IF EXISTS reducer_name,
    DROP COLUMN IF EXISTS reducer_version,
    DROP COLUMN IF EXISTS attempt_count,
    DROP COLUMN IF EXISTS retry_policy_version,
    DROP COLUMN IF EXISTS error_detail;

ALTER TABLE observer_plane.quarantine_events
    ADD CONSTRAINT ck_observer_quarantine_conflict_type
        CHECK (
            conflict_type IN (
                'EVENT_ID_HASH_CONFLICT',
                'STREAM_SEQUENCE_CONFLICT',
                'PREVIOUS_HASH_MISMATCH',
                'INVALID_SCHEMA_VERSION',
                'UNKNOWN_SOURCE_AUTHORITY'
            )
        ),
    ADD CONSTRAINT ck_observer_quarantine_reason_code
        CHECK (
            reason_code IN (
                'EVENT_ID_HASH_CONFLICT',
                'STREAM_SEQUENCE_CONFLICT',
                'PREVIOUS_HASH_MISMATCH',
                'INVALID_SCHEMA_VERSION',
                'UNKNOWN_SOURCE_AUTHORITY'
            )
        );
"""
