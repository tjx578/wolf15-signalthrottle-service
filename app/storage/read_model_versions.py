from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.storage.postgres import get_connection


class ReadModelVersionRepository:
    async def record(
        self,
        *,
        read_model_name: str,
        reducer_version: str,
        source_watermark: int | None,
        source_event_id: UUID | None,
        output_hash: str | None,
        rebuilt_at: datetime | None,
    ) -> None:
        async with get_connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO observer_plane.read_model_versions (
                        read_model_name,
                        reducer_version,
                        source_watermark,
                        source_event_id,
                        output_hash,
                        rebuilt_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
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
                        reducer_version,
                        source_watermark,
                        source_event_id,
                        output_hash,
                        rebuilt_at,
                    ),
                )
