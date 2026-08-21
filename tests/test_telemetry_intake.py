from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from app.contracts.observer_telemetry import (
    OBSERVER_TELEMETRY_SCHEMA_VERSION,
    ObserverTelemetryEvent,
    TelemetryIntakeStatus,
)
import app.services.telemetry_intake as intake_module
from app.services.telemetry_intake import TelemetryIntakeService


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _Connection:
    def __init__(self) -> None:
        self.locks: list[str] = []

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def execute(self, query, params=None):
        if "pg_advisory_xact_lock" in query:
            self.locks.append(params[0])
        return None


class _Ledger:
    def __init__(self) -> None:
        self.events: dict[object, dict] = {}
        self.sequences: dict[tuple[str, int], dict] = {}
        self.insert_calls = 0

    async def get_by_event_id(self, conn, event_id):
        return self.events.get(event_id)

    async def get_by_stream_sequence(self, conn, stream_id, stream_sequence):
        return self.sequences.get((stream_id, stream_sequence))

    async def insert(self, conn, event, *, source_authority, payload_hash):
        row = {
            "event_id": event.event_id,
            "stream_id": event.stream_id,
            "stream_sequence": event.stream_sequence,
            "payload_hash": payload_hash,
            "source_authority": source_authority,
        }
        self.events[event.event_id] = row
        if event.stream_sequence is not None:
            self.sequences[(event.stream_id, event.stream_sequence)] = row
        self.insert_calls += 1


class _Jobs:
    def __init__(self) -> None:
        self.insert_calls = 0

    async def insert_pending(self, conn, **kwargs):
        self.insert_calls += 1
        return uuid4()


class _Quarantine:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def insert(self, conn, **kwargs):
        self.rows.append(kwargs)
        return uuid4()


def _event(**overrides) -> ObserverTelemetryEvent:
    values = {
        "event_id": uuid4(),
        "stream_id": "legacy:USDJPY",
        "stream_sequence": 1,
        "event_type": "SIGNAL_THROTTLE",
        "source_authority": "LEGACY_DERIVED_LOG",
        "schema_version": OBSERVER_TELEMETRY_SCHEMA_VERSION,
        "occurred_at_utc": datetime(2026, 8, 21, 8, 0, tzinfo=UTC),
        "payload": {"symbol": "USDJPY", "count": 3},
    }
    values.update(overrides)
    return ObserverTelemetryEvent(**values)


def _service(monkeypatch):
    connection = _Connection()
    ledger = _Ledger()
    jobs = _Jobs()
    quarantine = _Quarantine()
    service = TelemetryIntakeService()
    service._ledger = ledger
    service._jobs = jobs
    service._quarantine = quarantine

    @asynccontextmanager
    async def connection_factory():
        yield connection

    monkeypatch.setattr(intake_module, "get_connection", connection_factory)
    return service, connection, ledger, jobs, quarantine


def test_valid_event_and_reducer_job_are_written_as_one_intake(monkeypatch) -> None:
    service, connection, ledger, jobs, quarantine = _service(monkeypatch)
    event = _event()

    result = asyncio.run(service.ingest(event))

    assert result.status == TelemetryIntakeStatus.ACCEPTED
    assert result.telemetry_rows_created == 1
    assert result.reducer_jobs_created == 1
    assert ledger.insert_calls == 1
    assert jobs.insert_calls == 1
    assert quarantine.rows == []
    assert ledger.events[event.event_id]["source_authority"] == "LEGACY_OBSERVATIONAL"
    assert connection.locks == [
        "observer-stream:legacy:USDJPY",
        f"observer-event:{event.event_id}",
    ]


def test_same_event_and_hash_is_idempotent(monkeypatch) -> None:
    service, _, ledger, jobs, quarantine = _service(monkeypatch)
    event = _event()

    first = asyncio.run(service.ingest(event))
    duplicate = asyncio.run(service.ingest(event))

    assert first.status == TelemetryIntakeStatus.ACCEPTED
    assert duplicate.status == TelemetryIntakeStatus.IDEMPOTENT_DUPLICATE
    assert ledger.insert_calls == 1
    assert jobs.insert_calls == 1
    assert quarantine.rows == []


def test_same_event_with_different_hash_is_quarantined(monkeypatch) -> None:
    service, _, ledger, jobs, quarantine = _service(monkeypatch)
    event = _event()
    asyncio.run(service.ingest(event))
    conflict = event.model_copy(update={"payload": {"symbol": "USDJPY", "count": 9}})

    result = asyncio.run(service.ingest(conflict))

    assert result.status == TelemetryIntakeStatus.EVENT_ID_HASH_CONFLICT
    assert ledger.insert_calls == 1
    assert jobs.insert_calls == 1
    assert quarantine.rows[-1]["reason_code"] == "EVENT_ID_HASH_CONFLICT"


def test_untrusted_authority_and_schema_version_are_quarantined(monkeypatch) -> None:
    service, _, ledger, jobs, quarantine = _service(monkeypatch)

    unknown = asyncio.run(service.ingest(_event(source_authority="client_admin")))
    invalid_schema = asyncio.run(
        service.ingest(_event(schema_version="observer.telemetry.v999"))
    )
    canonical_claim = asyncio.run(
        service.ingest(
            _event(
                event_id=uuid4(),
                stream_id="canonical-claim",
                stream_sequence=None,
                source_authority="CANONICAL_WOLF15",
            )
        )
    )
    explicit_unknown = asyncio.run(
        service.ingest(
            _event(
                event_id=uuid4(),
                stream_id="explicit-unknown",
                stream_sequence=None,
                source_authority="UNKNOWN",
            )
        )
    )

    assert unknown.status == TelemetryIntakeStatus.UNKNOWN_SOURCE_AUTHORITY
    assert invalid_schema.status == TelemetryIntakeStatus.INVALID_SCHEMA_VERSION
    assert canonical_claim.status == TelemetryIntakeStatus.UNKNOWN_SOURCE_AUTHORITY
    assert explicit_unknown.status == TelemetryIntakeStatus.ACCEPTED
    assert ledger.insert_calls == 1
    assert jobs.insert_calls == 1
    assert [row["reason_code"] for row in quarantine.rows] == [
        "UNKNOWN_SOURCE_AUTHORITY",
        "INVALID_SCHEMA_VERSION",
        "UNKNOWN_SOURCE_AUTHORITY",
    ]


def test_matching_previous_hash_extends_stream_chain(monkeypatch) -> None:
    service, _, ledger, jobs, quarantine = _service(monkeypatch)
    first = _event()
    second = _event(
        event_id=uuid4(),
        stream_sequence=2,
        previous_event_hash=first.calculate_payload_hash(),
        payload={"symbol": "USDJPY", "count": 4},
    )

    first_result = asyncio.run(service.ingest(first))
    second_result = asyncio.run(service.ingest(second))

    assert first_result.status == TelemetryIntakeStatus.ACCEPTED
    assert second_result.status == TelemetryIntakeStatus.ACCEPTED
    assert ledger.insert_calls == 2
    assert jobs.insert_calls == 2
    assert quarantine.rows == []
