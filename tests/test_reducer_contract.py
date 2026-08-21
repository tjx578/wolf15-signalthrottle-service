from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from app.contracts.reducer import (
    ClaimedReducerJob,
    ReducerErrorCode,
    ReducerFailure,
    RetryPolicy,
    calculate_output_hash,
    reduce_observer_event,
)


def _claim() -> ClaimedReducerJob:
    return ClaimedReducerJob(
        reducer_job_id=uuid4(),
        event_id=uuid4(),
        reducer_name="observer_pressure",
        reducer_version="observer-pressure-v1",
        attempt_count=1,
        lease_owner="worker-a",
        lease_token=uuid4(),
        stream_id="legacy:USDJPY",
        stream_sequence=7,
        event_type="SIGNAL_THROTTLE",
        input_payload_hash="a" * 64,
        payload={"count": 3, "symbol": "USDJPY"},
    )


def test_reference_reducer_hash_excludes_worker_and_attempt_metadata() -> None:
    first = _claim()
    recovered = replace(
        first,
        attempt_count=2,
        lease_owner="worker-after-restart",
        lease_token=uuid4(),
    )

    assert reduce_observer_event(first) == reduce_observer_event(recovered)
    assert calculate_output_hash(reduce_observer_event(first)) == (
        calculate_output_hash(reduce_observer_event(recovered))
    )


def test_retry_policy_is_bounded_versioned_and_fatal_errors_do_not_retry() -> None:
    policy = RetryPolicy(delays=(timedelta(seconds=2), timedelta(seconds=9)))

    assert policy.version == "observer-retry-v1"
    assert policy.max_attempts == 3
    assert policy.retry_delay(
        error_code=ReducerErrorCode.TRANSIENT_DEPENDENCY,
        attempt_count=1,
    ) == timedelta(seconds=2)
    assert policy.retry_delay(
        error_code=ReducerErrorCode.TRANSIENT_DEPENDENCY,
        attempt_count=2,
    ) == timedelta(seconds=9)
    assert policy.retry_delay(
        error_code=ReducerErrorCode.TRANSIENT_DEPENDENCY,
        attempt_count=3,
    ) is None
    for fatal in (
        ReducerErrorCode.INVALID_EVENT,
        ReducerErrorCode.HASH_CONFLICT,
        ReducerErrorCode.REDUCER_INVARIANT_FAILURE,
    ):
        assert policy.retry_delay(error_code=fatal, attempt_count=1) is None


def test_non_json_reducer_output_fails_closed() -> None:
    with pytest.raises(ReducerFailure) as failure:
        calculate_output_hash({"bad": {1, 2, 3}})

    assert failure.value.error_code == ReducerErrorCode.REDUCER_INVARIANT_FAILURE
