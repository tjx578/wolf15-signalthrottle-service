from __future__ import annotations

from pydantic import BaseModel


class DashboardStats(BaseModel):
    active_blocks: int = 0
    priority_signals: int = 0
    avg_density: str = "0.0"
    last_update: str = "-"
