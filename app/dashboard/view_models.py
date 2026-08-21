from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.models.source_authority import normalize_source_authority


class ActiveBlockView(BaseModel):
    symbol: str
    duration_minutes: float
    event_count: int
    density_per_minute: float
    max_gap_seconds: float | None
    pressure_grade: str
    finalize_mode: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ActiveBlockView":
        return cls(
            symbol=str(row.get("symbol") or "-"),
            duration_minutes=float(row.get("duration_minutes") or 0),
            event_count=int(row.get("event_count") or 0),
            density_per_minute=float(row.get("density_per_minute") or 0),
            max_gap_seconds=_float_or_none(row.get("max_gap_seconds")),
            pressure_grade=str(row.get("pressure_grade") or "-"),
            finalize_mode=_str_or_none(row.get("finalize_mode")),
        )


class PressureObservationView(BaseModel):
    id: int | None = None
    block_id: int | None = None
    symbol: str
    pressure_grade: str | None = None
    pressure_status: str | None = None
    end_wita: str | None = None
    density_per_minute: float | None = None
    duration_minutes: float | None = None
    event_count: int | None = None
    max_gap_seconds: float | None = None
    reason_code: str | None = None
    display_message: str | None = None
    observation_bucket: str | None = None
    source_authority: str = "UNKNOWN"
    raw_coverage: str = "RAW_COVERAGE_UNKNOWN"
    expected_pair_admission: str = "NOT_EVALUATED"
    consumer_authority: str = "OBSERVATIONAL_ONLY"
    valid_for_execution: bool = False
    execution_command_allowed: bool = False

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PressureObservationView":
        return cls(
            id=_int_or_none(row.get("id")),
            block_id=_int_or_none(row.get("block_id") or row.get("id")),
            symbol=str(row.get("symbol") or "-"),
            pressure_grade=_str_or_none(row.get("pressure_grade")),
            pressure_status=_str_or_none(row.get("pressure_status")),
            end_wita=_str_or_none(row.get("end_wita")),
            density_per_minute=_float_or_none(row.get("density_per_minute")),
            duration_minutes=_float_or_none(row.get("duration_minutes")),
            event_count=_int_or_none(row.get("event_count")),
            max_gap_seconds=_float_or_none(row.get("max_gap_seconds")),
            reason_code=_str_or_none(row.get("reason_code")),
            display_message=_str_or_none(row.get("display_message")),
            observation_bucket=_str_or_none(row.get("observation_bucket")),
            source_authority=normalize_source_authority(row.get("source_authority")),
            raw_coverage=str(row.get("raw_coverage") or "RAW_COVERAGE_UNKNOWN"),
            expected_pair_admission=str(
                row.get("expected_pair_admission") or "NOT_EVALUATED"
            ),
            consumer_authority="OBSERVATIONAL_ONLY",
            valid_for_execution=False,
            execution_command_allowed=False,
        )


def build_active_block_view(row: dict[str, Any]) -> dict[str, Any]:
    return ActiveBlockView.from_row(row).model_dump()


def build_pressure_observation_view(
    row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    return PressureObservationView.from_row(row).model_dump()


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
