from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
from psycopg.rows import DictRow


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
