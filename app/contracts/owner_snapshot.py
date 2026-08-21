from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OwnerObserverIdentityV1(BaseModel):
    commit_sha: str
    deployment_environment: str
    operating_mode: Literal["OBSERVE_ONLY"] = "OBSERVE_ONLY"
    authority: Literal["OBSERVATIONAL_ONLY"] = "OBSERVATIONAL_ONLY"


class OwnerSourceStateV1(BaseModel):
    committed_stream_sequence: int | None
    committed_event_id: UUID | None
    source_watermark: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_freshness_seconds: int | None = Field(default=None, ge=0)


class OwnerReadModelStateV1(BaseModel):
    generation_id: UUID
    reducer_versions: dict[str, str]
    generated_at_utc: datetime
    output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class OwnerContainmentStateV1(BaseModel):
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    phase2_surface_count: int = Field(ge=0)
    execution_surface_count: int = Field(ge=0)
    forbidden_artifact_count: int = Field(ge=0)


class OwnerDataQualityStateV1(BaseModel):
    status: Literal["PASS", "DEGRADED", "UNKNOWN"]
    sequence_gap_count: int = Field(ge=0)
    hash_conflict_count: int = Field(ge=0)
    quarantine_count: int = Field(ge=0)
    backlog_count: int = Field(ge=0)
    oldest_backlog_age_seconds: int | None = Field(default=None, ge=0)


class OwnerCanonicalFeedStateV1(BaseModel):
    status: Literal["HOLD_UPSTREAM_TYPED_EXPORT"] = "HOLD_UPSTREAM_TYPED_EXPORT"
    freshness: Literal["UNKNOWN"] = "UNKNOWN"


class OwnerBrokerStateV1(BaseModel):
    status: Literal["NOT_MEASURED"] = "NOT_MEASURED"


class OwnerIncidentCountsV1(BaseModel):
    sev0: int = Field(ge=0)
    sev1: int = Field(ge=0)
    sev2: int = Field(ge=0)
    info: int = Field(ge=0)


class OwnerCapabilitiesV1(BaseModel):
    replay: Literal["DISABLED_PENDING_DURABLE_ISOLATED_REPLAY"] = (
        "DISABLED_PENDING_DURABLE_ISOLATED_REPLAY"
    )
    canonical_reconciliation: Literal["HOLD_UPSTREAM_TYPED_EXPORT"] = (
        "HOLD_UPSTREAM_TYPED_EXPORT"
    )
    why_no_trade: Literal["HOLD_UPSTREAM_TYPED_EXPORT"] = (
        "HOLD_UPSTREAM_TYPED_EXPORT"
    )


class OwnerSystemSnapshotV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["owner.system-snapshot.v1"] = "owner.system-snapshot.v1"
    snapshot_id: UUID
    snapshot_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at_utc: datetime
    as_of_utc: datetime
    observer: OwnerObserverIdentityV1
    source: OwnerSourceStateV1
    read_models: OwnerReadModelStateV1
    containment: OwnerContainmentStateV1
    data_quality: OwnerDataQualityStateV1
    canonical_feed: OwnerCanonicalFeedStateV1
    broker_state: OwnerBrokerStateV1
    incidents: OwnerIncidentCountsV1
    capabilities: OwnerCapabilitiesV1


class OwnerReadModelResponseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["owner.read-model.v1"] = "owner.read-model.v1"
    snapshot_id: UUID
    source_watermark: str = Field(pattern=r"^[0-9a-f]{64}$")
    read_model_generation: UUID
    as_of_utc: datetime
    artifact_name: str
    artifact_version: str
    artifact_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    data: dict[str, Any]
