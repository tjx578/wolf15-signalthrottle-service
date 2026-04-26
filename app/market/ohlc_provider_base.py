from __future__ import annotations

from abc import ABC, abstractmethod


class OHLCProviderBase(ABC):
    @abstractmethod
    async def fetch(self, symbol: str, timeframe: str, bars: int = 200) -> list[dict]:
        ...
