from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LogEvent(BaseModel):
    id: int | None = None
    symbol: str
    event_type: str = "SIGNAL_THROTTLE"
    timestamp_utc: datetime
    timestamp_wita: str | None = None
    chart_time: str | None = None
    raw_message: str
    source_service: str = "wolf15-engine"
    created_at: datetime | None = None
