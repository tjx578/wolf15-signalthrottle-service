from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


class FinnhubClient:
    RESOLUTION = {
        "M15": "15",
        "H1": "60",
        "D1": "D",
    }

    def __init__(self, api_key: str, base_url: str = "https://finnhub.io/api/v1") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def convert_symbol(symbol: str) -> str:
        symbol = symbol.strip().upper()

        if ":" in symbol:
            return symbol

        if len(symbol) == 6:
            return f"OANDA:{symbol[:3]}_{symbol[3:]}"

        return symbol

    async def fetch(
        self,
        symbol: str,
        timeframe: str,
        bars: int = 200,
        end_time_utc: datetime | None = None,
    ) -> list[dict[str, Any]]:
        timeframe = timeframe.upper()

        if timeframe == "H4":
            h1 = await self.fetch(
                symbol=symbol,
                timeframe="H1",
                bars=bars * 4,
                end_time_utc=end_time_utc,
            )
            return self.aggregate_h4(h1)

        if timeframe not in self.RESOLUTION:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        end_time_utc = end_time_utc or datetime.now(timezone.utc)
        if end_time_utc.tzinfo is None:
            end_time_utc = end_time_utc.replace(tzinfo=timezone.utc)

        to_ts = int(end_time_utc.timestamp())

        if timeframe == "M15":
            delta = timedelta(minutes=int(bars * 15 * 1.5))
        elif timeframe == "H1":
            delta = timedelta(hours=int(bars * 1.5))
        else:
            delta = timedelta(days=int(bars * 1.5))

        from_ts = int((end_time_utc - delta).timestamp())

        params = {
            "symbol": self.convert_symbol(symbol),
            "resolution": self.RESOLUTION[timeframe],
            "from": from_ts,
            "to": to_ts,
            "token": self.api_key,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{self.base_url}/forex/candle", params=params)
            response.raise_for_status()
            data = response.json()

        if data.get("s") != "ok":
            return []

        candles: list[dict[str, Any]] = []

        for open_, high, low, close, volume, timestamp in zip(
            data.get("o", []),
            data.get("h", []),
            data.get("l", []),
            data.get("c", []),
            data.get("v", []),
            data.get("t", []),
        ):
            if open_ <= 0 or high <= 0 or low <= 0 or close <= 0:
                continue

            candles.append(
                {
                    "symbol": symbol.upper(),
                    "timeframe": timeframe,
                    "timestamp": datetime.fromtimestamp(timestamp, tz=timezone.utc),
                    "open": float(open_),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": float(volume or 0),
                    "source": "finnhub",
                }
            )

        return candles

    @staticmethod
    def aggregate_h4(h1_candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not h1_candles:
            return []

        result: list[dict[str, Any]] = []
        bucket: list[dict[str, Any]] = []

        for candle in sorted(h1_candles, key=lambda item: item["timestamp"]):
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
                        "volume": sum(float(x.get("volume", 0)) for x in bucket),
                        "source": "h1_aggregated",
                    }
                )
                bucket = []

        return result
