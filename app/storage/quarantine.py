from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb

from app.contracts.reducer import ClaimedReducerJob, ReducerErrorCode


class QuarantineRepository:
    async def insert(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        *,
        event_id: UUID,
        stream_id: str,
        stream_sequence: int | None,
        conflict_type: str,
        existing_payload_hash: str | None,
        received_payload_hash: str,
        received_payload: dict[str, Any],
        reason_code: str,
    ) -> UUID:
        quarantine_id = uuid4()
        await conn.execute(
            """
            INSERT INTO observer_plane.quarantine_events (
                quarantine_id,
                event_id,
                stream_id,
                stream_sequence,
                conflict_type,
                existing_payload_hash,
                received_payload_hash,
                received_payload,
                reason_code
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                quarantine_id,
                event_id,
                stream_id,
                stream_sequence,
                conflict_type,
                existing_payload_hash,
                received_payload_hash,
                Jsonb(received_payload),
                reason_code,
            ),
        )
        return quarantine_id

    async def insert_reducer_failure(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        *,
        claim: ClaimedReducerJob,
        error_code: ReducerErrorCode,
        reason_code: str,
        retry_policy_version: str,
        error_detail: str,
    ) -> UUID:
        quarantine_id = uuid4()
        await conn.execute(
            """
            INSERT INTO observer_plane.quarantine_events (
                quarantine_id,
                event_id,
                stream_id,
                stream_sequence,
                conflict_type,
                received_payload_hash,
                received_payload,
                reason_code
                ,reducer_job_id,
                reducer_name,
                reducer_version,
                attempt_count,
                retry_policy_version,
                error_detail
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                quarantine_id,
                claim.event_id,
                claim.stream_id,
                claim.stream_sequence,
                error_code.value,
                claim.input_payload_hash,
                Jsonb(claim.payload),
                reason_code,
                claim.reducer_job_id,
                claim.reducer_name,
                claim.reducer_version,
                claim.attempt_count,
                retry_policy_version,
                error_detail[:2048],
            ),
        )
        return quarantine_id
