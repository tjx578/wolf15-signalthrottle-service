from __future__ import annotations

from uuid import UUID

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
