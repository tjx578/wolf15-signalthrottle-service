from __future__ import annotations


OWNER_READ_MODEL_REVISION = "20260822_03_owner_snapshot_read_models"
OWNER_READ_MODEL_NAME = "owner-system-v1"
OWNER_READ_MODEL_TABLES = frozenset(
    {
        "read_model_generations",
        "read_model_current_generations",
        "read_model_artifacts",
        "observer_incidents",
    }
)
OWNER_GENERATION_COLUMNS = frozenset(
    {
        "source_start_sequence",
        "source_end_sequence",
        "source_watermark_hash",
        "reducer_versions",
        "validated_at",
    }
)


OWNER_READ_MODEL_UP_SQL = f"""
SELECT pg_advisory_xact_lock(
    hashtext('wolf15-signalthrottle-service:{OWNER_READ_MODEL_REVISION}')
);

ALTER TABLE observer_plane.read_model_generations
    ADD COLUMN IF NOT EXISTS source_start_sequence BIGINT,
    ADD COLUMN IF NOT EXISTS source_end_sequence BIGINT,
    ADD COLUMN IF NOT EXISTS source_watermark_hash CHAR(64),
    ADD COLUMN IF NOT EXISTS reducer_versions JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    ADD COLUMN IF NOT EXISTS validated_at TIMESTAMPTZ;

ALTER TABLE observer_plane.read_model_generations
    DROP CONSTRAINT IF EXISTS ck_observer_generation_status,
    DROP CONSTRAINT IF EXISTS ck_observer_generation_ready,
    DROP CONSTRAINT IF EXISTS ck_observer_generation_sequence_range,
    DROP CONSTRAINT IF EXISTS ck_observer_generation_watermark_hash,
    DROP CONSTRAINT IF EXISTS ck_observer_owner_generation_lifecycle;

ALTER TABLE observer_plane.read_model_generations
    ADD CONSTRAINT ck_observer_generation_status
        CHECK (
            status IN (
                'BUILDING', 'READY', 'CURRENT',
                'VALIDATED', 'ACTIVE', 'REJECTED', 'SUPERSEDED'
            )
        ),
    ADD CONSTRAINT ck_observer_generation_ready
        CHECK (
            status = 'BUILDING'
            OR (output_hash IS NOT NULL AND completed_at IS NOT NULL)
        ),
    ADD CONSTRAINT ck_observer_generation_sequence_range
        CHECK (
            source_start_sequence IS NULL
            OR source_end_sequence IS NULL
            OR source_end_sequence >= source_start_sequence
        ),
    ADD CONSTRAINT ck_observer_generation_watermark_hash
        CHECK (
            source_watermark_hash IS NULL
            OR source_watermark_hash ~ '^[0-9a-f]{{64}}$'
        ),
    ADD CONSTRAINT ck_observer_owner_generation_lifecycle
        CHECK (
            read_model_name <> '{OWNER_READ_MODEL_NAME}'
            OR status = 'BUILDING'
            OR (
                output_hash IS NOT NULL
                AND source_watermark_hash IS NOT NULL
                AND completed_at IS NOT NULL
                AND (
                    status = 'REJECTED'
                    OR validated_at IS NOT NULL
                )
            )
        );

CREATE UNIQUE INDEX IF NOT EXISTS uq_observer_active_generation_by_model
    ON observer_plane.read_model_generations (read_model_name)
    WHERE status = 'ACTIVE';

CREATE TABLE IF NOT EXISTS observer_plane.read_model_artifacts (
    generation_id UUID NOT NULL
        REFERENCES observer_plane.read_model_generations(generation_id)
        ON DELETE CASCADE,
    artifact_name TEXT NOT NULL CHECK (BTRIM(artifact_name) <> ''),
    artifact_version TEXT NOT NULL CHECK (BTRIM(artifact_version) <> ''),
    source_watermark_hash CHAR(64) NOT NULL,
    content_hash CHAR(64) NOT NULL,
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (generation_id, artifact_name),
    CONSTRAINT ck_observer_artifact_watermark_hash
        CHECK (source_watermark_hash ~ '^[0-9a-f]{{64}}$'),
    CONSTRAINT ck_observer_artifact_content_hash
        CHECK (content_hash ~ '^[0-9a-f]{{64}}$')
);

CREATE INDEX IF NOT EXISTS idx_observer_artifact_lookup
    ON observer_plane.read_model_artifacts (artifact_name, generation_id);

CREATE TABLE IF NOT EXISTS observer_plane.observer_incidents (
    incident_id UUID PRIMARY KEY,
    incident_type TEXT NOT NULL CHECK (BTRIM(incident_type) <> ''),
    severity TEXT NOT NULL CHECK (severity IN ('SEV0', 'SEV1', 'SEV2', 'INFO')),
    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'RESOLVED')),
    source_event_id UUID,
    source_watermark_hash CHAR(64),
    details JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    CONSTRAINT ck_observer_incident_watermark_hash
        CHECK (
            source_watermark_hash IS NULL
            OR source_watermark_hash ~ '^[0-9a-f]{{64}}$'
        ),
    CONSTRAINT ck_observer_incident_resolution
        CHECK (
            (status = 'OPEN' AND resolved_at IS NULL)
            OR (status = 'RESOLVED' AND resolved_at IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_observer_incidents_open
    ON observer_plane.observer_incidents (severity, detected_at, incident_id)
    WHERE status = 'OPEN';

INSERT INTO observer_plane.schema_revisions (revision_id)
VALUES ('{OWNER_READ_MODEL_REVISION}')
ON CONFLICT (revision_id) DO NOTHING;
"""


OWNER_READ_MODEL_DOWN_SQL = f"""
SELECT pg_advisory_xact_lock(
    hashtext('wolf15-signalthrottle-service:{OWNER_READ_MODEL_REVISION}')
);

DELETE FROM observer_plane.schema_revisions
WHERE revision_id = '{OWNER_READ_MODEL_REVISION}';

DROP TABLE IF EXISTS observer_plane.observer_incidents;
DROP TABLE IF EXISTS observer_plane.read_model_artifacts;
DROP INDEX IF EXISTS observer_plane.uq_observer_active_generation_by_model;

UPDATE observer_plane.read_model_generations
SET status = CASE
    WHEN status = 'VALIDATED' THEN 'READY'
    WHEN status = 'ACTIVE' THEN 'CURRENT'
    WHEN status = 'SUPERSEDED' THEN 'READY'
    ELSE status
END
WHERE status IN ('VALIDATED', 'ACTIVE', 'SUPERSEDED');

ALTER TABLE observer_plane.read_model_generations
    DROP CONSTRAINT IF EXISTS ck_observer_generation_status,
    DROP CONSTRAINT IF EXISTS ck_observer_generation_ready,
    DROP CONSTRAINT IF EXISTS ck_observer_generation_sequence_range,
    DROP CONSTRAINT IF EXISTS ck_observer_generation_watermark_hash,
    DROP CONSTRAINT IF EXISTS ck_observer_owner_generation_lifecycle;

ALTER TABLE observer_plane.read_model_generations
    ADD CONSTRAINT ck_observer_generation_status
        CHECK (status IN ('BUILDING', 'READY', 'CURRENT', 'REJECTED')),
    ADD CONSTRAINT ck_observer_generation_ready
        CHECK (
            status = 'BUILDING'
            OR (output_hash IS NOT NULL AND completed_at IS NOT NULL)
        );

ALTER TABLE observer_plane.read_model_generations
    DROP COLUMN IF EXISTS source_start_sequence,
    DROP COLUMN IF EXISTS source_end_sequence,
    DROP COLUMN IF EXISTS source_watermark_hash,
    DROP COLUMN IF EXISTS reducer_versions,
    DROP COLUMN IF EXISTS validated_at;
"""
