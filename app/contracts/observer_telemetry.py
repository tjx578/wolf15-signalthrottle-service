from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


OBSERVER_TELEMETRY_SCHEMA_VERSION = "observer.telemetry.v1"
SUPPORTED_OBSERVER_SCHEMA_VERSIONS = frozenset(
    {OBSERVER_TELEMETRY_SCHEMA_VERSION}
)
ALLOWED_INGEST_AUTHORITIES = frozenset({"LEGACY_OBSERVATIONAL", "UNKNOWN"})
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class TelemetryIntakeStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    IDEMPOTENT_DUPLICATE = "IDEMPOTENT_DUPLICATE"
    EVENT_ID_HASH_CONFLICT = "EVENT_ID_HASH_CONFLICT"
    STREAM_SEQUENCE_CONFLICT = "STREAM_SEQUENCE_CONFLICT"
    PREVIOUS_HASH_MISMATCH = "PREVIOUS_HASH_MISMATCH"
    INVALID_SCHEMA_VERSION = "INVALID_SCHEMA_VERSION"
    UNKNOWN_SOURCE_AUTHORITY = "UNKNOWN_SOURCE_AUTHORITY"


class ObserverTelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    stream_id: str = Field(min_length=1, max_length=255)
    stream_sequence: int | None = Field(default=None, ge=0)
    previous_event_hash: str | None = None
    event_type: str = Field(min_length=1, max_length=255)
    source_authority: str = Field(min_length=1, max_length=64)
    source_provenance: str | None = Field(default=None, max_length=255)
    source_commit_sha: str | None = Field(default=None, max_length=64)
    schema_version: str = Field(min_length=1, max_length=64)
    policy_version: str | None = Field(default=None, max_length=64)
    occurred_at_utc: datetime
    payload: dict[str, Any]

    @field_validator(
        "stream_id",
        "event_type",
        "source_authority",
        "schema_version",
    )
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("source_authority")
    @classmethod
    def _normalize_authority_case(cls, value: str) -> str:
        return value.upper()

    @field_validator("previous_event_hash")
    @classmethod
    def _validate_previous_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not _SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("previous_event_hash must be a lowercase SHA-256 hex digest")
        return normalized

    @field_validator("occurred_at_utc")
    @classmethod
    def _require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at_utc must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("payload")
    @classmethod
    def _require_json_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload must be canonical JSON data") from exc
        return value

    def canonical_payload_bytes(self) -> bytes:
        return json.dumps(
            self.payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")

    def calculate_payload_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload_bytes()).hexdigest()


class TelemetryIntakeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: TelemetryIntakeStatus
    event_id: UUID
    payload_hash: str
    telemetry_rows_created: int = 0
    reducer_jobs_created: int = 0
    quarantine_rows_created: int = 0
