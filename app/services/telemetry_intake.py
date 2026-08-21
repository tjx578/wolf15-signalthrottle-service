from __future__ import annotations

from app.contracts.observer_telemetry import (
    ALLOWED_INGEST_AUTHORITIES,
    SUPPORTED_OBSERVER_SCHEMA_VERSIONS,
    ObserverTelemetryEvent,
    TelemetryIntakeResult,
    TelemetryIntakeStatus,
)
from app.models.source_authority import normalize_source_authority
from app.storage.postgres import get_connection
from app.storage.quarantine import QuarantineRepository
from app.storage.reducer_jobs import ReducerJobRepository
from app.storage.telemetry_ledger import TelemetryLedgerRepository


class TelemetryIntakeService:
    def __init__(self) -> None:
        self._ledger = TelemetryLedgerRepository()
        self._jobs = ReducerJobRepository()
        self._quarantine = QuarantineRepository()

    async def ingest(
        self,
        event: ObserverTelemetryEvent,
        *,
        reducer_name: str = "observer_pressure",
        reducer_version: str = "observer-pressure-v1",
    ) -> TelemetryIntakeResult:
        payload_hash = event.calculate_payload_hash()
        normalized_authority = normalize_source_authority(event.source_authority)
        authority_is_known = (
            event.source_authority == "UNKNOWN"
            or normalized_authority != "UNKNOWN"
        )

        async with get_connection() as conn:
            async with conn.transaction():
                if not authority_is_known or normalized_authority not in ALLOWED_INGEST_AUTHORITIES:
                    return await self._quarantine_result(
                        conn,
                        event,
                        payload_hash,
                        TelemetryIntakeStatus.UNKNOWN_SOURCE_AUTHORITY,
                    )

                if event.schema_version not in SUPPORTED_OBSERVER_SCHEMA_VERSIONS:
                    return await self._quarantine_result(
                        conn,
                        event,
                        payload_hash,
                        TelemetryIntakeStatus.INVALID_SCHEMA_VERSION,
                    )

                if event.stream_sequence is not None:
                    await self._lock(
                        conn,
                        f"observer-stream:{event.stream_id}",
                    )
                await self._lock(conn, f"observer-event:{event.event_id}")

                existing_event = await self._ledger.get_by_event_id(
                    conn,
                    event.event_id,
                )
                if existing_event is not None:
                    if existing_event["payload_hash"] == payload_hash:
                        return TelemetryIntakeResult(
                            status=TelemetryIntakeStatus.IDEMPOTENT_DUPLICATE,
                            event_id=event.event_id,
                            payload_hash=payload_hash,
                        )
                    return await self._quarantine_result(
                        conn,
                        event,
                        payload_hash,
                        TelemetryIntakeStatus.EVENT_ID_HASH_CONFLICT,
                        existing_payload_hash=existing_event["payload_hash"],
                    )

                if event.stream_sequence is not None:
                    sequence_event = await self._ledger.get_by_stream_sequence(
                        conn,
                        event.stream_id,
                        event.stream_sequence,
                    )
                    if sequence_event is not None:
                        return await self._quarantine_result(
                            conn,
                            event,
                            payload_hash,
                            TelemetryIntakeStatus.STREAM_SEQUENCE_CONFLICT,
                            existing_payload_hash=sequence_event["payload_hash"],
                        )

                    if event.previous_event_hash is not None:
                        previous_sequence = event.stream_sequence - 1
                        previous_event = (
                            await self._ledger.get_by_stream_sequence(
                                conn,
                                event.stream_id,
                                previous_sequence,
                            )
                            if previous_sequence >= 0
                            else None
                        )
                        if (
                            previous_event is None
                            or previous_event["payload_hash"]
                            != event.previous_event_hash
                        ):
                            return await self._quarantine_result(
                                conn,
                                event,
                                payload_hash,
                                TelemetryIntakeStatus.PREVIOUS_HASH_MISMATCH,
                                existing_payload_hash=(
                                    previous_event["payload_hash"]
                                    if previous_event is not None
                                    else None
                                ),
                            )

                await self._ledger.insert(
                    conn,
                    event,
                    source_authority=normalized_authority,
                    payload_hash=payload_hash,
                )
                await self._jobs.insert_pending(
                    conn,
                    event_id=event.event_id,
                    reducer_name=reducer_name,
                    reducer_version=reducer_version,
                )
                return TelemetryIntakeResult(
                    status=TelemetryIntakeStatus.ACCEPTED,
                    event_id=event.event_id,
                    payload_hash=payload_hash,
                    telemetry_rows_created=1,
                    reducer_jobs_created=1,
                )

    async def _quarantine_result(
        self,
        conn,
        event: ObserverTelemetryEvent,
        payload_hash: str,
        status: TelemetryIntakeStatus,
        *,
        existing_payload_hash: str | None = None,
    ) -> TelemetryIntakeResult:
        await self._quarantine.insert(
            conn,
            event_id=event.event_id,
            stream_id=event.stream_id,
            stream_sequence=event.stream_sequence,
            conflict_type=status.value,
            existing_payload_hash=existing_payload_hash,
            received_payload_hash=payload_hash,
            received_payload=event.payload,
            reason_code=status.value,
        )
        return TelemetryIntakeResult(
            status=status,
            event_id=event.event_id,
            payload_hash=payload_hash,
            quarantine_rows_created=1,
        )

    @staticmethod
    async def _lock(conn, identity: str) -> None:
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (identity,),
        )
