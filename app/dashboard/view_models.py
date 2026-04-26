from __future__ import annotations

from pydantic import BaseModel


class ActiveBlockView(BaseModel):
    symbol: str
    duration_minutes: float
    event_count: int
    density_per_minute: float
    max_gap_seconds: float | None
    pressure_grade: str
    finalize_mode: str | None


class TradeSignalView(BaseModel):
    id: int
    symbol: str
    pressure_grade: str
    execution_grade: str
    action: str
    signal_end_wita: str | None
    chart_phase: str | None
