from __future__ import annotations

import json

from typing import Any

from pydantic import BaseModel


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


class TradeSignalView(BaseModel):
    id: int | None = None
    trade_plan_id: int | None = None
    block_id: int | None = None
    symbol: str
    pressure_grade: str | None = None
    execution_grade: str | None = None
    action: str | None = None
    signal_end_wita: str | None
    chart_phase: str | None
    market_context_status: str | None = None
    trade_plan_status: str | None = None
    density_per_minute: float | None = None
    density_state: str | None = None
    duration_minutes: float | None = None
    event_count: int | None = None
    max_gap_seconds: float | None = None
    reason_code: str | None = None
    display_message: str | None = None
    message: str | None = None
    dashboard_bucket: str | None = None
    owner_alert: str | None = None
    h4_structure: str | None = None
    h4_context_type: str | None = None
    standalone_grade: str | None = None
    chain_adjusted_grade: str | None = None
    chain_type: str | None = None
    execution_mode: str | None = None
    previous_block_grade: str | None = None
    previous_block_end_wita: str | None = None
    gap_from_previous_minutes: float | None = None
    grade_note: str | None = None
    payload: dict[str, Any] | list[Any] | str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "TradeSignalView":
        payload = _normalize_payload(row.get("payload"))
        snapshot = payload.get("snapshot") if isinstance(payload, dict) else {}
        chain_context = payload.get("chain_context") if isinstance(payload, dict) else {}
        return cls(
            id=_int_or_none(row.get("id")),
            trade_plan_id=_int_or_none(row.get("trade_plan_id")),
            block_id=_int_or_none(row.get("block_id") or row.get("id")),
            symbol=str(row.get("symbol") or "-"),
            pressure_grade=_str_or_none(row.get("pressure_grade")),
            execution_grade=_str_or_none(row.get("execution_grade")),
            action=_str_or_none(row.get("action")),
            signal_end_wita=_str_or_none(row.get("signal_end_wita") or row.get("end_wita")),
            chart_phase=_str_or_none(row.get("chart_phase")),
            market_context_status=_str_or_none(row.get("market_context_status")),
            trade_plan_status=_str_or_none(row.get("trade_plan_status")),
            density_per_minute=_float_or_none(row.get("density_per_minute")),
            density_state=_str_or_none(row.get("density_state")),
            duration_minutes=_float_or_none(row.get("duration_minutes")),
            event_count=_int_or_none(row.get("event_count")),
            max_gap_seconds=_float_or_none(row.get("max_gap_seconds")),
            reason_code=_str_or_none(row.get("reason_code")),
            display_message=_str_or_none(row.get("display_message") or row.get("message")),
            message=_str_or_none(row.get("message")),
            dashboard_bucket=_str_or_none(row.get("dashboard_bucket")),
            owner_alert=_str_or_none(row.get("owner_alert")),
            h4_structure=_str_or_none(row.get("h4_structure") or snapshot.get("h4_structure")),
            h4_context_type=_str_or_none(row.get("h4_context_type") or snapshot.get("h4_context_type")),
            standalone_grade=_str_or_none(row.get("standalone_grade") or chain_context.get("standalone_grade")),
            chain_adjusted_grade=_str_or_none(row.get("chain_adjusted_grade") or chain_context.get("chain_adjusted_grade")),
            chain_type=_str_or_none(row.get("chain_type") or chain_context.get("chain_type")),
            execution_mode=_str_or_none(row.get("execution_mode") or chain_context.get("execution_mode")),
            previous_block_grade=_str_or_none(row.get("previous_block_grade") or chain_context.get("previous_block_grade")),
            previous_block_end_wita=_str_or_none(row.get("previous_block_end_wita") or chain_context.get("previous_block_end_wita")),
            gap_from_previous_minutes=_float_or_none(
                row.get("gap_from_previous_minutes") or chain_context.get("gap_from_previous_minutes")
            ),
            grade_note=_str_or_none(row.get("grade_note")),
            payload=payload,
        )


def build_active_block_view(row: dict[str, Any]) -> dict[str, Any]:
    return ActiveBlockView.from_row(row).model_dump()


def build_trade_signal_view(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return TradeSignalView.from_row(row).model_dump()


def _normalize_payload(payload: Any) -> dict[str, Any] | list[Any] | str | None:
    if payload is None:
        return None
    if isinstance(payload, (dict, list)):
        return payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return payload
        if isinstance(parsed, (dict, list)):
            return parsed
        return payload
    return str(payload)


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
