from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.contracts.observer_telemetry import (
    OBSERVER_TELEMETRY_SCHEMA_VERSION,
    ObserverTelemetryEvent,
)


def _event(**overrides) -> ObserverTelemetryEvent:
    values = {
        "event_id": uuid4(),
        "stream_id": "legacy:USDJPY",
        "stream_sequence": 1,
        "event_type": "SIGNAL_THROTTLE",
        "source_authority": "legacy_observational",
        "schema_version": OBSERVER_TELEMETRY_SCHEMA_VERSION,
        "occurred_at_utc": datetime(2026, 8, 21, 8, 0, tzinfo=UTC),
        "payload": {"symbol": "USDJPY", "count": 3},
    }
    values.update(overrides)
    return ObserverTelemetryEvent(**values)


def test_payload_hash_is_canonical_and_authority_case_is_normalized() -> None:
    first = _event(payload={"count": 3, "symbol": "USDJPY"})
    second = _event(payload={"symbol": "USDJPY", "count": 3})

    assert first.calculate_payload_hash() == second.calculate_payload_hash()
    assert len(first.calculate_payload_hash()) == 64
    assert first.source_authority == "LEGACY_OBSERVATIONAL"
    assert first.occurred_at_utc.tzinfo is UTC


def test_contract_preserves_legacy_alias_for_intake_normalization() -> None:
    event = _event(source_authority="legacy_derived_log")

    assert event.source_authority == "LEGACY_DERIVED_LOG"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("occurred_at_utc", datetime(2026, 8, 21, 8, 0)),
        ("previous_event_hash", "not-a-sha256"),
        ("stream_id", "   "),
        ("event_type", ""),
    ],
)
def test_contract_rejects_ambiguous_or_invalid_event_fields(field, value) -> None:
    with pytest.raises(ValidationError):
        _event(**{field: value})


def test_contract_rejects_non_json_payload() -> None:
    with pytest.raises(ValidationError, match="canonical JSON"):
        _event(payload={"unsupported": {1, 2, 3}})
