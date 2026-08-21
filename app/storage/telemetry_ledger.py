from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import DictRow
from psycopg.types.json import Jsonb

from app.contracts.observer_telemetry import ObserverTelemetryEvent


class TelemetryLedgerRepository:
    async def get_by_event_id(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        event_id: object,
    ) -> dict[str, Any] | None:
        cursor = await conn.execute(
            """
            SELECT event_id, stream_id, stream_sequence, payload_hash
            FROM observer_plane.telemetry_events
            WHERE event_id = %s
            """,
            (event_id,),
        )
        return await cursor.fetchone()

    async def get_by_stream_sequence(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        stream_id: str,
        stream_sequence: int,
    ) -> dict[str, Any] | None:
        cursor = await conn.execute(
            """
            SELECT event_id, stream_id, stream_sequence, payload_hash
            FROM observer_plane.telemetry_events
            WHERE stream_id = %s AND stream_sequence = %s
            """,
            (stream_id, stream_sequence),
        )
        return await cursor.fetchone()

    async def insert(
        self,
        conn: "psycopg.AsyncConnection[DictRow]",
        event: ObserverTelemetryEvent,
        *,
        source_authority: str,
        payload_hash: str,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO observer_plane.telemetry_events (
                event_id,
                stream_id,
                stream_sequence,
                previous_event_hash,
                event_type,
                source_authority,
                source_provenance,
                source_commit_sha,
                schema_version,
                policy_version,
                occurred_at_utc,
                payload_hash,
                payload
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                event.event_id,
                event.stream_id,
                event.stream_sequence,
                event.previous_event_hash,
                event.event_type,
                source_authority,
                event.source_provenance,
                event.source_commit_sha,
                event.schema_version,
                event.policy_version,
                event.occurred_at_utc,
                payload_hash,
                Jsonb(event.payload),
            ),
        )
