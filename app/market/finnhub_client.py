from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.market.ohlc_provider_base import OHLCProviderBase

logger = logging.getLogger(__name__)


class FinnhubClient(OHLCProviderBase):
    RESOLUTION = {
        "M15": "15",
        "H1": "60",
        "D1": "D",
    }

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://finnhub.io/api/v1",
    ):
        self.api_key = api_key
        self.base_url = base_url

    @staticmethod
    def convert_symbol(symbol: str) -> str:
        if ":" in symbol:
            return symbol
        if len(symbol) == 6 and symbol.isalpha():
            return f"OANDA:{symbol[:3]}_{symbol[3:]}"
        return symbol

    async def fetch(
        self, symbol: str, timeframe: str, bars: int = 200
    ) -> list[dict]:
        if timeframe == "H4":
            h1 = await self.fetch(symbol, "H1", bars * 4)
            return self._aggregate_h4(h1)

        resolution = self.RESOLUTION.get(timeframe)
        if not resolution:
            logger.warning("Unknown timeframe: %s", timeframe)
            return []

        to_ts = int(datetime.now(timezone.utc).timestamp())

        if timeframe == "M15":
            delta = timedelta(minutes=int(bars * 15 * 1.4))
        elif timeframe == "H1":
            delta = timedelta(hours=int(bars * 1.4))
        else:
            delta = timedelta(days=int(bars * 1.4))

        from_ts = int((datetime.now(timezone.utc) - delta).timestamp())

        params = {
            "symbol": self.convert_symbol(symbol),
            "resolution": resolution,
            "from": from_ts,
            "to": to_ts,
            "token": self.api_key,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.get(f"{self.base_url}/forex/candle", params=params)
            res.raise_for_status()
            data = res.json()

        if data.get("s") != "ok":
            return []

        return [
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": datetime.fromtimestamp(t, tz=timezone.utc).isoformat(),
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "volume": v,
                "source": "finnhub",
            }
            for o, h, lo, c, v, t in zip(
                data["o"], data["h"], data["l"], data["c"], data["v"], data["t"]
            )
            if o > 0 and h > 0 and lo > 0 and c > 0
        ]

    @staticmethod
    def _aggregate_h4(h1: list[dict]) -> list[dict]:
        result = []
        bucket: list[dict] = []

        for candle in h1:
            bucket.append(candle)
            if len(bucket) == 4:
                result.append(
                    {
                        "symbol": bucket[0]["symbol"],
                        "timeframe": "H4",
                        "timestamp": bucket[-1]["timestamp"],
                        "open": bucket[0]["open"],
                        "high": max(x["high"] for x in bucket),
                        "low": min(x["low"] for x in bucket),
                        "close": bucket[-1]["close"],
                        "volume": sum(x["volume"] for x in bucket),
                        "source": "h1_aggregated",
                    }
                )
                bucket = []

        return result
