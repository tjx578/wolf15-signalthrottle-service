from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.contracts.reducer import calculate_output_hash
from app.storage.read_model_generations import ReadModelGenerationRepository
from app.storage.telemetry_ledger import TelemetryLedgerRepository


RebuildReducer = Callable[
    [list[dict[str, Any]], str],
    dict[str, Any] | Awaitable[dict[str, Any]],
]


class RebuildStatus(StrEnum):
    READY = "READY"
    CURRENT = "CURRENT"
    HASH_MISMATCH = "HASH_MISMATCH"


@dataclass(frozen=True)
class RebuildResult:
    status: RebuildStatus
    generation_id: UUID
    output_hash: str
    source_watermark: int | None
    source_event_id: UUID | None


def rebuild_event_index(
    events: list[dict[str, Any]],
    reducer_version: str,
) -> dict[str, Any]:
    """Reference deterministic rebuild from immutable observer ledger rows."""

    return {
        "reducer_version": reducer_version,
        "events": [
            {
                "event_id": str(event["event_id"]),
                "event_type": event["event_type"],
                "payload": event["payload"],
                "payload_hash": event["payload_hash"],
                "stream_id": event["stream_id"],
                "stream_sequence": event["stream_sequence"],
            }
            for event in events
        ],
    }


class ReadModelRebuildService:
    def __init__(self) -> None:
        self._ledger = TelemetryLedgerRepository()
        self._generations = ReadModelGenerationRepository()

    async def rebuild(
        self,
        *,
        read_model_name: str,
        reducer_version: str,
        source_stream_id: str | None = None,
        reducer: RebuildReducer = rebuild_event_index,
        expected_output_hash: str | None = None,
        promote: bool = False,
    ) -> RebuildResult:
        generation_id = await self._generations.create_building(
            read_model_name=read_model_name,
            reducer_version=reducer_version,
            source_stream_id=source_stream_id,
        )
        events = await self._ledger.list_for_rebuild(stream_id=source_stream_id)
        output = reducer(events, reducer_version)
        if inspect.isawaitable(output):
            output = await output
        if not isinstance(output, dict):
            raise ValueError("read-model reducer output must be a JSON object")
        output_hash = calculate_output_hash(output)

        sequenced = [event for event in events if event["stream_sequence"] is not None]
        watermark_event = max(
            sequenced,
            key=lambda event: (event["stream_sequence"], str(event["event_id"])),
            default=None,
        )
        source_watermark = (
            watermark_event["stream_sequence"] if watermark_event else None
        )
        source_event_id = watermark_event["event_id"] if watermark_event else None

        if expected_output_hash is not None and output_hash != expected_output_hash:
            await self._generations.mark_rejected(
                generation_id=generation_id,
                source_watermark=source_watermark,
                source_event_id=source_event_id,
                output_hash=output_hash,
                output=output,
            )
            return RebuildResult(
                status=RebuildStatus.HASH_MISMATCH,
                generation_id=generation_id,
                output_hash=output_hash,
                source_watermark=source_watermark,
                source_event_id=source_event_id,
            )

        ready = await self._generations.mark_ready(
            generation_id=generation_id,
            source_watermark=source_watermark,
            source_event_id=source_event_id,
            output_hash=output_hash,
            output=output,
        )
        if not ready:
            raise RuntimeError("read-model generation is no longer BUILDING")

        status = RebuildStatus.READY
        if promote:
            if not await self._generations.promote(generation_id=generation_id):
                raise RuntimeError("read-model generation could not be promoted")
            status = RebuildStatus.CURRENT

        return RebuildResult(
            status=status,
            generation_id=generation_id,
            output_hash=output_hash,
            source_watermark=source_watermark,
            source_event_id=source_event_id,
        )
