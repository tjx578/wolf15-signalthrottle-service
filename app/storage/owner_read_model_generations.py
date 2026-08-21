from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.storage.owner_read_model_schema import OWNER_READ_MODEL_NAME
from app.storage.postgres import get_connection


@dataclass(frozen=True)
class ReadModelArtifact:
    name: str
    version: str
    source_watermark_hash: str
    content_hash: str
    content: dict[str, Any]


class OwnerReadModelGenerationRepository:
    async def create_building(
        self,
        *,
        reducer_versions: dict[str, str],
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
                        reducer_versions,
                        status
                    ) VALUES (%s, %s, %s, %s, 'BUILDING')
                    """,
                    (
                        generation_id,
                        OWNER_READ_MODEL_NAME,
                        "owner-read-models-v1",
                        Jsonb(reducer_versions),
                    ),
                )
        return generation_id

    async def validate(
        self,
        *,
        generation_id: UUID,
        source_start_sequence: int | None,
        source_end_sequence: int | None,
        source_event_id: UUID | None,
        source_watermark_hash: str,
        output_hash: str,
        manifest: dict[str, Any],
        artifacts: tuple[ReadModelArtifact, ...],
    ) -> bool:
        if not artifacts:
            raise ValueError("owner generation requires artifacts")
        if any(
            artifact.source_watermark_hash != source_watermark_hash
            for artifact in artifacts
        ):
            raise ValueError("all artifacts must use the generation watermark")

        async with get_connection() as conn:
            async with conn.transaction():
                cursor = await conn.execute(
                    """
                    SELECT status
                    FROM observer_plane.read_model_generations
                    WHERE generation_id = %s AND read_model_name = %s
                    FOR UPDATE
                    """,
                    (generation_id, OWNER_READ_MODEL_NAME),
                )
                generation = await cursor.fetchone()
                if generation is None or generation["status"] != "BUILDING":
                    return False

                for artifact in artifacts:
                    await conn.execute(
                        """
                        INSERT INTO observer_plane.read_model_artifacts (
                            generation_id,
                            artifact_name,
                            artifact_version,
                            source_watermark_hash,
                            content_hash,
                            content
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            generation_id,
                            artifact.name,
                            artifact.version,
                            artifact.source_watermark_hash,
                            artifact.content_hash,
                            Jsonb(artifact.content),
                        ),
                    )

                updated = await conn.execute(
                    """
                    UPDATE observer_plane.read_model_generations
                    SET status = 'VALIDATED',
                        source_start_sequence = %s,
                        source_end_sequence = %s,
                        source_watermark = %s,
                        source_event_id = %s,
                        source_watermark_hash = %s,
                        output_hash = %s,
                        output = %s,
                        completed_at = NOW(),
                        validated_at = NOW()
                    WHERE generation_id = %s AND status = 'BUILDING'
                    RETURNING generation_id
                    """,
                    (
                        source_start_sequence,
                        source_end_sequence,
                        source_end_sequence,
                        source_event_id,
                        source_watermark_hash,
                        output_hash,
                        Jsonb(manifest),
                        generation_id,
                    ),
                )
                return await updated.fetchone() is not None

    async def reject(
        self,
        *,
        generation_id: UUID,
        source_start_sequence: int | None,
        source_end_sequence: int | None,
        source_event_id: UUID | None,
        source_watermark_hash: str,
        output_hash: str,
        manifest: dict[str, Any],
    ) -> bool:
        async with get_connection() as conn:
            async with conn.transaction():
                cursor = await conn.execute(
                    """
                    UPDATE observer_plane.read_model_generations
                    SET status = 'REJECTED',
                        source_start_sequence = %s,
                        source_end_sequence = %s,
                        source_watermark = %s,
                        source_event_id = %s,
                        source_watermark_hash = %s,
                        output_hash = %s,
                        output = %s,
                        completed_at = NOW()
                    WHERE generation_id = %s
                      AND read_model_name = %s
                      AND status = 'BUILDING'
                    RETURNING generation_id
                    """,
                    (
                        source_start_sequence,
                        source_end_sequence,
                        source_end_sequence,
                        source_event_id,
                        source_watermark_hash,
                        output_hash,
                        Jsonb(manifest),
                        generation_id,
                        OWNER_READ_MODEL_NAME,
                    ),
                )
                return await cursor.fetchone() is not None

    async def promote(self, *, generation_id: UUID) -> bool:
        """Atomically replace the active owner generation.

        Readers see the old or the new committed pointer. The partial unique
        index is a database-level backstop against two ACTIVE generations.
        """

        async with get_connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"observer-read-model:{OWNER_READ_MODEL_NAME}",),
                )
                cursor = await conn.execute(
                    """
                    SELECT *
                    FROM observer_plane.read_model_generations
                    WHERE generation_id = %s AND read_model_name = %s
                    FOR UPDATE
                    """,
                    (generation_id, OWNER_READ_MODEL_NAME),
                )
                candidate = await cursor.fetchone()
                if candidate is None:
                    return False
                if candidate["status"] == "ACTIVE":
                    return True
                if candidate["status"] != "VALIDATED":
                    return False

                active_cursor = await conn.execute(
                    """
                    SELECT generation.*
                    FROM observer_plane.read_model_current_generations AS current
                    JOIN observer_plane.read_model_generations AS generation
                      ON generation.generation_id = current.generation_id
                    WHERE current.read_model_name = %s
                    FOR UPDATE OF generation
                    """,
                    (OWNER_READ_MODEL_NAME,),
                )
                active = await active_cursor.fetchone()
                if active is not None:
                    candidate_end = candidate["source_end_sequence"]
                    active_end = active["source_end_sequence"]
                    if (
                        candidate_end is not None
                        and active_end is not None
                        and candidate_end < active_end
                    ):
                        return False
                    if candidate["output_hash"] == active["output_hash"]:
                        return False
                    await conn.execute(
                        """
                        UPDATE observer_plane.read_model_generations
                        SET status = 'SUPERSEDED'
                        WHERE generation_id = %s AND status = 'ACTIVE'
                        """,
                        (active["generation_id"],),
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
                    (OWNER_READ_MODEL_NAME, generation_id),
                )
                await conn.execute(
                    """
                    UPDATE observer_plane.read_model_generations
                    SET status = 'ACTIVE', promoted_at = NOW()
                    WHERE generation_id = %s AND status = 'VALIDATED'
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
                        OWNER_READ_MODEL_NAME,
                        candidate["reducer_version"],
                        candidate["source_end_sequence"],
                        candidate["source_event_id"],
                        candidate["output_hash"],
                    ),
                )
        return True

    async def get_active_bundle(
        self,
    ) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]] | None:
        async with get_connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
                cursor = await conn.execute(
                    """
                    SELECT generation.*
                    FROM observer_plane.read_model_current_generations AS current
                    JOIN observer_plane.read_model_generations AS generation
                      ON generation.generation_id = current.generation_id
                    WHERE current.read_model_name = %s
                      AND generation.status = 'ACTIVE'
                    """,
                    (OWNER_READ_MODEL_NAME,),
                )
                generation = await cursor.fetchone()
                if generation is None:
                    return None
                artifact_cursor = await conn.execute(
                    """
                    SELECT *
                    FROM observer_plane.read_model_artifacts
                    WHERE generation_id = %s
                    ORDER BY artifact_name
                    """,
                    (generation["generation_id"],),
                )
                artifacts = tuple(await artifact_cursor.fetchall())
                return generation, artifacts

    async def count_active(self) -> int:
        async with get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM observer_plane.read_model_generations
                WHERE read_model_name = %s AND status = 'ACTIVE'
                """,
                (OWNER_READ_MODEL_NAME,),
            )
            row = await cursor.fetchone()
            return int(row["count"])
