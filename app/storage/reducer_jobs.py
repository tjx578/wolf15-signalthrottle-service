from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import DictRow

from app.contracts.reducer import ClaimedReducerJob, ReducerErrorCode
from app.storage.postgres import get_connection


class ReducerJobRepository:
    async def insert_pending(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        *,
        event_id: UUID,
        reducer_name: str,
        reducer_version: str,
    ) -> UUID:
        reducer_job_id = uuid4()
        await conn.execute(
            """
            INSERT INTO observer_plane.reducer_jobs (
                reducer_job_id,
                event_id,
                reducer_name,
                reducer_version,
                status
            ) VALUES (%s, %s, %s, %s, 'PENDING')
            """,
            (reducer_job_id, event_id, reducer_name, reducer_version),
        )
        return reducer_job_id

    async def claim_next(
        self,
        *,
        lease_owner: str,
        lease_duration: timedelta,
        reducer_name: str | None = None,
        reducer_version: str | None = None,
    ) -> ClaimedReducerJob | None:
        if not lease_owner.strip():
            raise ValueError("lease_owner must not be blank")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")

        lease_token = uuid4()
        async with get_connection() as conn:
            async with conn.transaction():
                cursor = await conn.execute(
                    """
                    WITH candidate AS (
                        SELECT job.reducer_job_id
                        FROM observer_plane.reducer_jobs AS job
                        WHERE (
                            job.status = 'PENDING'
                            OR (
                                job.status = 'RETRY_WAIT'
                                AND job.next_attempt_at <= NOW()
                            )
                            OR (
                                job.status = 'LEASED'
                                AND job.lease_expires_at <= NOW()
                            )
                        )
                          AND (%s::TEXT IS NULL OR job.reducer_name = %s)
                          AND (%s::TEXT IS NULL OR job.reducer_version = %s)
                        ORDER BY job.created_at, job.reducer_job_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    ), claimed AS (
                        UPDATE observer_plane.reducer_jobs AS job
                        SET status = 'LEASED',
                            attempt_count = job.attempt_count + 1,
                            lease_owner = %s,
                            lease_token = %s,
                            leased_at = NOW(),
                            lease_expires_at = NOW() + %s,
                            next_attempt_at = NULL,
                            last_error_code = NULL,
                            last_error_detail = NULL,
                            updated_at = NOW()
                        FROM candidate
                        WHERE job.reducer_job_id = candidate.reducer_job_id
                        RETURNING job.*
                    )
                    SELECT
                        claimed.reducer_job_id,
                        claimed.event_id,
                        claimed.reducer_name,
                        claimed.reducer_version,
                        claimed.attempt_count,
                        claimed.lease_owner,
                        claimed.lease_token,
                        event.stream_id,
                        event.stream_sequence,
                        event.event_type,
                        event.payload_hash AS input_payload_hash,
                        event.payload
                    FROM claimed
                    JOIN observer_plane.telemetry_events AS event
                      ON event.event_id = claimed.event_id
                    """,
                    (
                        reducer_name,
                        reducer_name,
                        reducer_version,
                        reducer_version,
                        lease_owner,
                        lease_token,
                        lease_duration,
                    ),
                )
                row = await cursor.fetchone()

        if row is None:
            return None
        return ClaimedReducerJob(**row)

    async def mark_done(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        *,
        claim: ClaimedReducerJob,
        output_hash: str,
    ) -> bool:
        cursor = await conn.execute(
            """
            UPDATE observer_plane.reducer_jobs
            SET status = 'DONE',
                output_hash = %s,
                completed_at = NOW(),
                lease_owner = NULL,
                lease_token = NULL,
                leased_at = NULL,
                lease_expires_at = NULL,
                next_attempt_at = NULL,
                last_error_code = NULL,
                last_error_detail = NULL,
                updated_at = NOW()
            WHERE reducer_job_id = %s
              AND status = 'LEASED'
              AND lease_owner = %s
              AND lease_token = %s
              AND lease_expires_at > NOW()
            RETURNING reducer_job_id
            """,
            (
                output_hash,
                claim.reducer_job_id,
                claim.lease_owner,
                claim.lease_token,
            ),
        )
        return await cursor.fetchone() is not None

    async def schedule_retry(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        *,
        claim: ClaimedReducerJob,
        error_code: ReducerErrorCode,
        error_detail: str,
        next_attempt_at: datetime,
        retry_policy_version: str,
    ) -> bool:
        return await self._finish_attempt(
            conn,
            claim=claim,
            status="RETRY_WAIT",
            error_code=error_code,
            error_detail=error_detail,
            next_attempt_at=next_attempt_at,
            retry_policy_version=retry_policy_version,
        )

    async def mark_quarantined(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        *,
        claim: ClaimedReducerJob,
        error_code: ReducerErrorCode,
        error_detail: str,
        retry_policy_version: str,
    ) -> bool:
        return await self._finish_attempt(
            conn,
            claim=claim,
            status="QUARANTINED",
            error_code=error_code,
            error_detail=error_detail,
            next_attempt_at=None,
            retry_policy_version=retry_policy_version,
        )

    async def _finish_attempt(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        *,
        claim: ClaimedReducerJob,
        status: str,
        error_code: ReducerErrorCode,
        error_detail: str,
        next_attempt_at: datetime | None,
        retry_policy_version: str,
    ) -> bool:
        cursor = await conn.execute(
            """
            UPDATE observer_plane.reducer_jobs
            SET status = %s,
                lease_owner = NULL,
                lease_token = NULL,
                leased_at = NULL,
                lease_expires_at = NULL,
                next_attempt_at = %s,
                last_error_code = %s,
                last_error_detail = %s,
                retry_policy_version = %s,
                updated_at = NOW()
            WHERE reducer_job_id = %s
              AND status = 'LEASED'
              AND lease_owner = %s
              AND lease_token = %s
              AND lease_expires_at > NOW()
            RETURNING reducer_job_id
            """,
            (
                status,
                next_attempt_at,
                error_code.value,
                error_detail[:2048],
                retry_policy_version,
                claim.reducer_job_id,
                claim.lease_owner,
                claim.lease_token,
            ),
        )
        return await cursor.fetchone() is not None

    async def get(self, reducer_job_id: UUID) -> dict[str, Any] | None:
        async with get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT *
                FROM observer_plane.reducer_jobs
                WHERE reducer_job_id = %s
                """,
                (reducer_job_id,),
            )
            return await cursor.fetchone()
