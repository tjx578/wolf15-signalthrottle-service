from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.rows import DictRow

from app.storage.postgres import get_connection


class ConsumerCursorRepository:
    async def advance(
        self,
        *,
        consumer_name: str,
        stream_id: str,
        committed_sequence: int,
        committed_event_id: UUID,
        committed_payload_hash: str,
    ) -> bool:
        if committed_sequence < 0:
            raise ValueError("committed_sequence must not be negative")

        async with get_connection() as conn:
            async with conn.transaction():
                cursor = await conn.execute(
                    """
                    INSERT INTO observer_plane.consumer_cursors (
                        consumer_name,
                        stream_id,
                        committed_sequence,
                        committed_event_id,
                        committed_payload_hash
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (consumer_name, stream_id) DO UPDATE
                    SET committed_sequence = EXCLUDED.committed_sequence,
                        committed_event_id = EXCLUDED.committed_event_id,
                        committed_payload_hash = EXCLUDED.committed_payload_hash,
                        updated_at = NOW()
                    WHERE observer_plane.consumer_cursors.committed_sequence IS NULL
                       OR EXCLUDED.committed_sequence
                          > observer_plane.consumer_cursors.committed_sequence
                    RETURNING committed_sequence
                    """,
                    (
                        consumer_name,
                        stream_id,
                        committed_sequence,
                        committed_event_id,
                        committed_payload_hash,
                    ),
                )
                return await cursor.fetchone() is not None

    async def advance_contiguous(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        *,
        consumer_name: str,
        stream_id: str,
        reducer_name: str,
        reducer_version: str,
        allow_terminal_quarantine: bool = False,
        batch_size: int = 1000,
    ) -> int | None:
        """Advance only across contiguous sequences with terminal durable work."""

        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        await conn.execute(
            """
            INSERT INTO observer_plane.consumer_cursors (
                consumer_name, stream_id, committed_sequence
            ) VALUES (%s, %s, NULL)
            ON CONFLICT (consumer_name, stream_id) DO NOTHING
            """,
            (consumer_name, stream_id),
        )
        cursor = await conn.execute(
            """
            SELECT committed_sequence
            FROM observer_plane.consumer_cursors
            WHERE consumer_name = %s AND stream_id = %s
            FOR UPDATE
            """,
            (consumer_name, stream_id),
        )
        cursor_row = await cursor.fetchone()
        committed = (
            cursor_row["committed_sequence"] if cursor_row is not None else None
        )

        if committed is None:
            cursor = await conn.execute(
                """
                SELECT MIN(stream_sequence) AS first_sequence
                FROM observer_plane.telemetry_events
                WHERE stream_id = %s AND stream_sequence IS NOT NULL
                """,
                (stream_id,),
            )
            first_row = await cursor.fetchone()
            start_sequence = first_row["first_sequence"] if first_row else None
            if start_sequence is None:
                return None
        else:
            start_sequence = committed + 1

        cursor = await conn.execute(
            """
            SELECT
                event.stream_sequence,
                event.event_id,
                event.payload_hash,
                COUNT(job.reducer_job_id) AS required_job_count,
                COALESCE(BOOL_AND(job.status = 'DONE'), FALSE) AS all_done,
                COALESCE(
                    BOOL_AND(job.status IN ('DONE', 'QUARANTINED')),
                    FALSE
                ) AS all_terminal
            FROM observer_plane.telemetry_events AS event
            LEFT JOIN observer_plane.reducer_jobs AS job
              ON job.event_id = event.event_id
             AND job.reducer_name = %s
             AND job.reducer_version = %s
            WHERE event.stream_id = %s
              AND event.stream_sequence >= %s
            GROUP BY event.stream_sequence, event.event_id, event.payload_hash
            ORDER BY event.stream_sequence
            LIMIT %s
            """,
            (
                reducer_name,
                reducer_version,
                stream_id,
                start_sequence,
                batch_size,
            ),
        )
        rows = await cursor.fetchall()

        expected = start_sequence
        last_eligible = None
        for row in rows:
            if row["stream_sequence"] != expected:
                break
            eligible = bool(row["all_done"])
            if allow_terminal_quarantine:
                eligible = bool(row["all_terminal"])
            if row["required_job_count"] < 1 or not eligible:
                break
            last_eligible = row
            expected += 1

        if last_eligible is None:
            return committed

        await conn.execute(
            """
            UPDATE observer_plane.consumer_cursors
            SET committed_sequence = %s,
                committed_event_id = %s,
                committed_payload_hash = %s,
                updated_at = NOW()
            WHERE consumer_name = %s AND stream_id = %s
            """,
            (
                last_eligible["stream_sequence"],
                last_eligible["event_id"],
                last_eligible["payload_hash"],
                consumer_name,
                stream_id,
            ),
        )
        return last_eligible["stream_sequence"]
