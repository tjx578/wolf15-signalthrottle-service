from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PressureBlock(BaseModel):
    id: int | None = None
    symbol: str

    start_utc: datetime
    end_utc: datetime
    start_wita: str | None = None
    end_wita: str | None = None
    chart_start_time: str | None = None
    chart_end_time: str | None = None

    duration_minutes: float
    event_count: int
    density_per_minute: float
    avg_gap_seconds: float | None = None
    max_gap_seconds: float | None = None

    pressure_grade: str
    pressure_status: str | None = None
    block_relation: str | None = None
    previous_block_id: int | None = None
    finalize_mode: str | None = None

    is_active: bool = False
    created_at: datetime | None = None
