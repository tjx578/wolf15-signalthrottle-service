from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TradePlan(BaseModel):
    id: int | None = None
    block_id: int | None = None
    symbol: str
    signal_type: str = "SIGNAL_THROTTLE_PRESSURE"

    pressure_status: str | None = None
    signal_bucket: str | None = None
    pressure_grade: str
    execution_grade: str
    execution_side: str

    signal_start_utc: datetime
    signal_end_utc: datetime
    signal_start_wita: str | None = None
    signal_end_wita: str | None = None
    chart_time_start: str | None = None
    chart_time_end: str | None = None

    duration_minutes: float
    event_count: int
    density_per_minute: float
    max_gap_seconds: float | None = None
    avg_gap_seconds: float | None = None

    block_relation: str | None = None
    finalize_mode: str | None = None

    price_at_signal_end: str | None = None
    chart_bias: str | None = None
    chart_phase: str | None = None

    action: str
    entry_zone: str | None = None
    breakout_level: str | None = None
    reclaim_level: str | None = None
    invalidation: str | None = None

    tp1: str | None = None
    tp2: str | None = None
    tp3: str | None = None

    message: str = ""
    payload: dict = Field(default_factory=dict)
    created_at: datetime | None = None
