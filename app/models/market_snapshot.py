from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MarketSnapshot(BaseModel):
    id: int | None = None
    block_id: int | None = None
    symbol: str

    price_at_start: float | None = None
    price_at_end: float | None = None
    spread_points: float | None = None

    d1_bias: str | None = None
    h4_structure: str | None = None
    h1_phase: str | None = None
    m15_phase: str | None = None
    chart_bias: str | None = None
    chart_phase: str | None = None

    support_zone: str | None = None
    resistance_zone: str | None = None
    key_level: str | None = None

    raw_ohlc: dict | None = None
    created_at: datetime | None = None
