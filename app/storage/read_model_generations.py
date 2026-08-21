from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.storage.postgres import get_connection


class ReadModelGenerationRepository:
    async def create_building(
        self,
        *,
        read_model_name: str,
        reducer_version: str,
        source_stream_id: str | None,
    ) -> UUID:
        generation_id = uuid4()
        async with get_connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO observer_plane.read_model_generations (
                        generation_id,
                        read_model_name,
                        reducer_version,
                        status,
                        source_stream_id
                    ) VALUES (%s, %s, %s, 'BUILDING', %s)
                    """,
                    (
                        generation_id,
                        read_model_name,
                        reducer_version,
                        source_stream_id,
                    ),
                )
        return generation_id

    async def mark_ready(
        self,
        *,
        generation_id: UUID,
        source_watermark: int | None,
        source_event_id: UUID | None,
        output_hash: str,
        output: dict[str, Any],
    ) -> bool:
        async with get_connection() as conn:
            async with conn.transaction():
                cursor = await conn.execute(
                    """
                    UPDATE observer_plane.read_model_generations
                    SET status = 'READY',
                        source_watermark = %s,
                        source_event_id = %s,
                        output_hash = %s,
                        output = %s,
                        completed_at = NOW()
                    WHERE generation_id = %s AND status = 'BUILDING'
                    RETURNING generation_id
                    """,
                    (
                        source_watermark,
                        source_event_id,
                        output_hash,
                        Jsonb(output),
                        generation_id,
                    ),
                )
                return await cursor.fetchone() is not None

    async def mark_rejected(
        self,
        *,
        generation_id: UUID,
        source_watermark: int | None,
        source_event_id: UUID | None,
        output_hash: str,
        output: dict[str, Any],
    ) -> bool:
        async with get_connection() as conn:
            async with conn.transaction():
                cursor = await conn.execute(
                    """
                    UPDATE observer_plane.read_model_generations
                    SET status = 'REJECTED',
                        source_watermark = %s,
                        source_event_id = %s,
                        output_hash = %s,
                        output = %s,
                        completed_at = NOW()
                    WHERE generation_id = %s AND status = 'BUILDING'
                    RETURNING generation_id
                    """,
                    (
                        source_watermark,
                        source_event_id,
                        output_hash,
                        Jsonb(output),
                        generation_id,
                    ),
                )
                return await cursor.fetchone() is not None

    async def promote(self, *, generation_id: UUID) -> bool:
        async with get_connection() as conn:
            async with conn.transaction():
                cursor = await conn.execute(
                    """
                    SELECT *
                    FROM observer_plane.read_model_generations
                    WHERE generation_id = %s
                    FOR UPDATE
                    """,
                    (generation_id,),
                )
                generation = await cursor.fetchone()
                if generation is None or generation["status"] not in {
                    "READY",
                    "CURRENT",
                }:
                    return False

                read_model_name = generation["read_model_name"]
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"observer-read-model:{read_model_name}",),
                )
                await conn.execute(
                    """
                    UPDATE observer_plane.read_model_generations
                    SET status = 'READY', promoted_at = NULL
                    WHERE read_model_name = %s
                      AND status = 'CURRENT'
                      AND generation_id <> %s
                    """,
                    (read_model_name, generation_id),
                )
                await conn.execute(
                    """
                    INSERT INTO observer_plane.read_model_current_generations (
                        read_model_name, generation_id, promoted_at
                    ) VALUES (%s, %s, NOW())
                    ON CONFLICT (read_model_name) DO UPDATE
                    SET generation_id = EXCLUDED.generation_id,
                        promoted_at = EXCLUDED.promoted_at
                    """,
                    (read_model_name, generation_id),
                )
                await conn.execute(
                    """
                    UPDATE observer_plane.read_model_generations
                    SET status = 'CURRENT', promoted_at = NOW()
                    WHERE generation_id = %s
                    """,
                    (generation_id,),
                )
                await conn.execute(
                    """
                    INSERT INTO observer_plane.read_model_versions (
                        read_model_name,
                        reducer_version,
                        source_watermark,
                        source_event_id,
                        output_hash,
                        rebuilt_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (read_model_name) DO UPDATE
                    SET reducer_version = EXCLUDED.reducer_version,
                        source_watermark = EXCLUDED.source_watermark,
                        source_event_id = EXCLUDED.source_event_id,
                        output_hash = EXCLUDED.output_hash,
                        rebuilt_at = EXCLUDED.rebuilt_at,
                        updated_at = NOW()
                    """,
                    (
                        read_model_name,
                        generation["reducer_version"],
                        generation["source_watermark"],
                        generation["source_event_id"],
                        generation["output_hash"],
                    ),
                )
        return True

    async def get_current(self, read_model_name: str) -> dict[str, Any] | None:
        async with get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT generation.*
                FROM observer_plane.read_model_current_generations AS current
                JOIN observer_plane.read_model_generations AS generation
                  ON generation.generation_id = current.generation_id
                WHERE current.read_model_name = %s
                """,
                (read_model_name,),
            )
            return await cursor.fetchone()
