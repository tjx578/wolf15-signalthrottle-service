from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Awaitable, Callable

import psycopg

from app.contracts.reducer import (
    FATAL_REDUCER_ERROR_CODES,
    ClaimedReducerJob,
    ReducerErrorCode,
    ReducerFailure,
    RetryPolicy,
    calculate_output_hash,
    reduce_observer_event,
)
from app.storage.consumer_cursors import ConsumerCursorRepository
from app.storage.postgres import get_connection
from app.storage.quarantine import QuarantineRepository
from app.storage.reducer_jobs import ReducerJobRepository
from app.storage.reducer_outputs import ReducerOutputRepository


ReducerCallable = Callable[
    [ClaimedReducerJob],
    dict[str, Any] | Awaitable[dict[str, Any]],
]


class ReducerRunStatus(StrEnum):
    IDLE = "IDLE"
    DONE = "DONE"
    RETRY_WAIT = "RETRY_WAIT"
    QUARANTINED = "QUARANTINED"
    STALE_LEASE = "STALE_LEASE"


@dataclass(frozen=True)
class ReducerRunResult:
    status: ReducerRunStatus
    reducer_job_id: object | None = None
    attempt_count: int = 0
    output_hash: str | None = None
    committed_sequence: int | None = None
    error_code: ReducerErrorCode | None = None


class DurableReducerWorker:
    def __init__(
        self,
        *,
        lease_owner: str,
        reducer_name: str = "observer_pressure",
        reducer_version: str = "observer-pressure-v1",
        reducer: ReducerCallable = reduce_observer_event,
        retry_policy: RetryPolicy | None = None,
        lease_duration: timedelta = timedelta(seconds=30),
        consumer_name: str | None = None,
        allow_terminal_quarantine_cursor: bool = False,
    ) -> None:
        if not lease_owner.strip():
            raise ValueError("lease_owner must not be blank")
        self.lease_owner = lease_owner
        self.reducer_name = reducer_name
        self.reducer_version = reducer_version
        self.reducer = reducer
        self.retry_policy = retry_policy or RetryPolicy()
        self.lease_duration = lease_duration
        self.consumer_name = consumer_name or reducer_name
        self.allow_terminal_quarantine_cursor = allow_terminal_quarantine_cursor
        self._jobs = ReducerJobRepository()
        self._outputs = ReducerOutputRepository()
        self._quarantine = QuarantineRepository()
        self._cursors = ConsumerCursorRepository()

    async def run_once(self) -> ReducerRunResult:
        claim = await self._jobs.claim_next(
            lease_owner=self.lease_owner,
            lease_duration=self.lease_duration,
            reducer_name=self.reducer_name,
            reducer_version=self.reducer_version,
        )
        if claim is None:
            return ReducerRunResult(status=ReducerRunStatus.IDLE)
        return await self.process_claim(claim)

    async def process_claim(self, claim: ClaimedReducerJob) -> ReducerRunResult:
        try:
            output = self.reducer(claim)
            if inspect.isawaitable(output):
                output = await output
            if not isinstance(output, dict):
                raise ReducerFailure(
                    ReducerErrorCode.REDUCER_INVARIANT_FAILURE,
                    "reducer output must be a JSON object",
                )
            output_hash = calculate_output_hash(output)
        except ReducerFailure as exc:
            return await self._record_failure(
                claim,
                error_code=exc.error_code,
                detail=exc.detail,
            )
        except psycopg.Error as exc:
            return await self._record_failure(
                claim,
                error_code=ReducerErrorCode.TRANSIENT_DATABASE,
                detail=type(exc).__name__,
            )
        except Exception as exc:
            return await self._record_failure(
                claim,
                error_code=ReducerErrorCode.UNKNOWN,
                detail=f"{type(exc).__name__}: {exc}",
            )

        async with get_connection() as conn:
            async with conn.transaction():
                updated = await self._jobs.mark_done(
                    conn,
                    claim=claim,
                    output_hash=output_hash,
                )
                if not updated:
                    return ReducerRunResult(
                        status=ReducerRunStatus.STALE_LEASE,
                        reducer_job_id=claim.reducer_job_id,
                        attempt_count=claim.attempt_count,
                    )
                await self._outputs.insert(
                    conn,
                    claim=claim,
                    output_hash=output_hash,
                    output=output,
                )
                committed_sequence = await self._advance_cursor(conn, claim)
        return ReducerRunResult(
            status=ReducerRunStatus.DONE,
            reducer_job_id=claim.reducer_job_id,
            attempt_count=claim.attempt_count,
            output_hash=output_hash,
            committed_sequence=committed_sequence,
        )

    async def _record_failure(
        self,
        claim: ClaimedReducerJob,
        *,
        error_code: ReducerErrorCode,
        detail: str,
    ) -> ReducerRunResult:
        retry_delay = self.retry_policy.retry_delay(
            error_code=error_code,
            attempt_count=claim.attempt_count,
        )
        is_fatal = error_code in FATAL_REDUCER_ERROR_CODES
        async with get_connection() as conn:
            async with conn.transaction():
                if retry_delay is not None:
                    updated = await self._jobs.schedule_retry(
                        conn,
                        claim=claim,
                        error_code=error_code,
                        error_detail=detail,
                        next_attempt_at=datetime.now(UTC) + retry_delay,
                        retry_policy_version=self.retry_policy.version,
                    )
                    status = ReducerRunStatus.RETRY_WAIT
                    committed_sequence = None
                else:
                    updated = await self._jobs.mark_quarantined(
                        conn,
                        claim=claim,
                        error_code=error_code,
                        error_detail=detail,
                        retry_policy_version=self.retry_policy.version,
                    )
                    status = ReducerRunStatus.QUARANTINED
                    committed_sequence = None
                    if updated:
                        await self._quarantine.insert_reducer_failure(
                            conn,
                            claim=claim,
                            error_code=error_code,
                            reason_code=(
                                error_code.value if is_fatal else "RETRY_EXHAUSTED"
                            ),
                            retry_policy_version=self.retry_policy.version,
                            error_detail=detail,
                        )
                        committed_sequence = await self._advance_cursor(conn, claim)

                if not updated:
                    return ReducerRunResult(
                        status=ReducerRunStatus.STALE_LEASE,
                        reducer_job_id=claim.reducer_job_id,
                        attempt_count=claim.attempt_count,
                        error_code=error_code,
                    )

        return ReducerRunResult(
            status=status,
            reducer_job_id=claim.reducer_job_id,
            attempt_count=claim.attempt_count,
            committed_sequence=committed_sequence,
            error_code=error_code,
        )

    async def _advance_cursor(self, conn, claim: ClaimedReducerJob) -> int | None:
        if claim.stream_sequence is None:
            return None
        return await self._cursors.advance_contiguous(
            conn,
            consumer_name=self.consumer_name,
            stream_id=claim.stream_id,
            reducer_name=claim.reducer_name,
            reducer_version=claim.reducer_version,
            allow_terminal_quarantine=self.allow_terminal_quarantine_cursor,
        )
