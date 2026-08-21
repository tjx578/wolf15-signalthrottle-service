from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID


REDUCER_POLICY_VERSION = "observer-retry-v1"


class ReducerJobStatus(StrEnum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    DONE = "DONE"
    RETRY_WAIT = "RETRY_WAIT"
    QUARANTINED = "QUARANTINED"


class ReducerErrorCode(StrEnum):
    TRANSIENT_DATABASE = "TRANSIENT_DATABASE"
    TRANSIENT_DEPENDENCY = "TRANSIENT_DEPENDENCY"
    INVALID_EVENT = "INVALID_EVENT"
    HASH_CONFLICT = "HASH_CONFLICT"
    REDUCER_INVARIANT_FAILURE = "REDUCER_INVARIANT_FAILURE"
    UNKNOWN = "UNKNOWN"


FATAL_REDUCER_ERROR_CODES = frozenset(
    {
        ReducerErrorCode.INVALID_EVENT,
        ReducerErrorCode.HASH_CONFLICT,
        ReducerErrorCode.REDUCER_INVARIANT_FAILURE,
    }
)


@dataclass(frozen=True)
class RetryPolicy:
    """Versioned, bounded retry policy whose schedule survives worker restarts."""

    version: str = REDUCER_POLICY_VERSION
    delays: tuple[timedelta, ...] = (
        timedelta(seconds=1),
        timedelta(seconds=5),
        timedelta(seconds=30),
        timedelta(minutes=2),
        timedelta(minutes=5),
    )

    @property
    def max_attempts(self) -> int:
        return len(self.delays) + 1

    def retry_delay(
        self,
        *,
        error_code: ReducerErrorCode,
        attempt_count: int,
    ) -> timedelta | None:
        if attempt_count < 1:
            raise ValueError("attempt_count must be at least one after a claim")
        if error_code in FATAL_REDUCER_ERROR_CODES:
            return None
        if attempt_count > len(self.delays):
            return None
        return self.delays[attempt_count - 1]


@dataclass(frozen=True)
class ClaimedReducerJob:
    reducer_job_id: UUID
    event_id: UUID
    reducer_name: str
    reducer_version: str
    attempt_count: int
    lease_owner: str
    lease_token: UUID
    stream_id: str
    stream_sequence: int | None
    event_type: str
    input_payload_hash: str
    payload: dict[str, Any]


class Reducer(Protocol):
    def __call__(self, job: ClaimedReducerJob) -> dict[str, Any]: ...


class ReducerFailure(Exception):
    def __init__(self, error_code: ReducerErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.error_code = error_code
        self.detail = detail


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReducerFailure(
            ReducerErrorCode.REDUCER_INVARIANT_FAILURE,
            "reducer output must be canonical JSON data",
        ) from exc


def calculate_output_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def reduce_observer_event(job: ClaimedReducerJob) -> dict[str, Any]:
    """Reference deterministic reducer; deliberately excludes operational metadata."""

    return {
        "event_id": str(job.event_id),
        "event_type": job.event_type,
        "input_payload_hash": job.input_payload_hash,
        "payload": job.payload,
        "reducer_name": job.reducer_name,
        "reducer_version": job.reducer_version,
        "stream_id": job.stream_id,
        "stream_sequence": job.stream_sequence,
    }
