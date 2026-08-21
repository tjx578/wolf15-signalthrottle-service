from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb

from app.contracts.reducer import ClaimedReducerJob
from app.storage.postgres import get_connection


class ReducerOutputRepository:
    async def insert(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        *,
        claim: ClaimedReducerJob,
        output_hash: str,
        output: dict[str, Any],
    ) -> None:
        await conn.execute(
            """
            INSERT INTO observer_plane.reducer_outputs (
                reducer_job_id,
                event_id,
                reducer_name,
                reducer_version,
                input_payload_hash,
                output_hash,
                output
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                claim.reducer_job_id,
                claim.event_id,
                claim.reducer_name,
                claim.reducer_version,
                claim.input_payload_hash,
                output_hash,
                Jsonb(output),
            ),
        )

    async def get(self, reducer_job_id: UUID) -> dict[str, Any] | None:
        async with get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT *
                FROM observer_plane.reducer_outputs
                WHERE reducer_job_id = %s
                """,
                (reducer_job_id,),
            )
            return await cursor.fetchone()
