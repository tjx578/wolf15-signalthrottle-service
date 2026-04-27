from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Protocol


class OHLCProviderBase(Protocol):
    async def fetch(
        self,
        symbol: str,
        timeframe: str,
        bars: int = 200,
        end_time_utc: datetime | None = None,
    ) -> list[dict[str, Any]]:
        ...
