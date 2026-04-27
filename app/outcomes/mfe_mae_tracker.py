"""MFE/MAE tracker — Phase 4.

Pulls OHLC candles around a trade plan's signal_end_utc and computes
Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE)
across 15m / 30m / 60m windows, then classifies the outcome.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.market.finnhub_client import FinnhubClient
from app.outcomes.outcome_classifier import classify_outcome

logger = logging.getLogger(__name__)


def pip_size(symbol: str) -> float:
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def default_thresholds(symbol: str) -> tuple[float, float]:
    pip = pip_size(symbol)
    min_good_mfe = 18 * pip
    max_good_mae = 10 * pip
    return min_good_mfe, max_good_mae


_BUY_SIDES = {
    "BUY_CONTINUATION",
    "WAIT_SUPPORT_REACTION_OR_RECLAIM",
}

_SELL_SIDES = {
    "SELL_REJECTION_OR_EXIT_LONG",
    "PROTECT_LONG_OR_SELL_REJECTION",
    "SELL_ON_RALLY_OR_CONTINUATION",
}


def infer_direction(execution_side: str | None) -> str:
    if not execution_side:
        return "NEUTRAL"
    if execution_side in _BUY_SIDES:
        return "BUY"
    if execution_side in _SELL_SIDES:
        return "SELL"
    return "NEUTRAL"


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def window_candles(
    candles: list[dict[str, Any]],
    start: datetime,
    minutes: int,
) -> list[dict[str, Any]]:
    end = start + timedelta(minutes=minutes)
    result: list[dict[str, Any]] = []
    for candle in candles:
        ts = _coerce_datetime(candle.get("timestamp"))
        if ts is None:
            continue
        if start <= ts <= end:
            result.append(candle)
    return result


def calculate_mfe_mae(
    *,
    symbol: str,
    execution_side: str | None,
    entry_price: float,
    candles: list[dict[str, Any]],
    signal_end_utc: datetime,
    minutes: int,
) -> tuple[float | None, float | None, float | None]:
    data = window_candles(candles, signal_end_utc, minutes)
    if not data:
        return None, None, None

    direction = infer_direction(execution_side)
    highest = max(float(c["high"]) for c in data)
    lowest = min(float(c["low"]) for c in data)
    last_close = float(data[-1]["close"])

    if direction == "BUY":
        return highest - entry_price, entry_price - lowest, last_close
    if direction == "SELL":
        return entry_price - lowest, highest - entry_price, last_close
    return None, None, last_close


class MFEMAETracker:
    def __init__(self, ohlc_client: FinnhubClient) -> None:
        self.ohlc_client = ohlc_client

    async def evaluate(self, trade_plan: dict[str, Any]) -> dict[str, Any]:
        symbol = trade_plan["symbol"]
        payload = trade_plan.get("payload") or {}

        signal_end_utc = (
            _coerce_datetime(payload.get("signal_end_utc"))
            or _coerce_datetime(trade_plan.get("signal_end_utc"))
            or _coerce_datetime(trade_plan.get("created_at"))
        )

        execution_side = (
            trade_plan.get("execution_side")
            or payload.get("execution_side")
        )
        direction = infer_direction(execution_side)

        price_raw = (
            payload.get("price_at_signal_end")
            or payload.get("price_at_signal")
            or trade_plan.get("price_at_end")
        )

        chart_phase = payload.get("chart_phase") or trade_plan.get("chart_phase")
        snapshot = payload.get("snapshot") or {}
        h4_context_type = payload.get("h4_context_type") or snapshot.get("h4_context_type") or trade_plan.get("h4_context_type")

        base_record: dict[str, Any] = {
            "symbol": symbol,
            "pressure_grade": trade_plan.get("pressure_grade"),
            "execution_grade": trade_plan.get("execution_grade"),
            "chart_phase": chart_phase,
            "h4_context_type": h4_context_type,
            "execution_side": execution_side,
            "signal_end_utc": signal_end_utc,
            "price_at_signal": None,
            "price_after_15m": None,
            "price_after_30m": None,
            "price_after_60m": None,
            "mfe_15m": None,
            "mae_15m": None,
            "mfe_30m": None,
            "mae_30m": None,
            "mfe_60m": None,
            "mae_60m": None,
            "result_label": "PENDING",
            "raw_result": {},
        }

        if price_raw is None or signal_end_utc is None:
            base_record["result_label"] = "PENDING_NO_PRICE"
            base_record["raw_result"] = {"reason": "missing price or signal_end_utc"}
            return base_record

        entry_price = float(price_raw)
        base_record["price_at_signal"] = entry_price

        try:
            candles = await self.ohlc_client.fetch(
                symbol=symbol,
                timeframe="M15",
                bars=80,
                end_time_utc=signal_end_utc + timedelta(minutes=75),
            )
        except Exception as exc:
            logger.warning("OHLC fetch failed for %s: %s", symbol, exc)
            candles = []

        mfe_15m, mae_15m, price_after_15m = calculate_mfe_mae(
            symbol=symbol,
            execution_side=execution_side,
            entry_price=entry_price,
            candles=candles,
            signal_end_utc=signal_end_utc,
            minutes=15,
        )
        mfe_30m, mae_30m, price_after_30m = calculate_mfe_mae(
            symbol=symbol,
            execution_side=execution_side,
            entry_price=entry_price,
            candles=candles,
            signal_end_utc=signal_end_utc,
            minutes=30,
        )
        mfe_60m, mae_60m, price_after_60m = calculate_mfe_mae(
            symbol=symbol,
            execution_side=execution_side,
            entry_price=entry_price,
            candles=candles,
            signal_end_utc=signal_end_utc,
            minutes=60,
        )

        min_good_mfe, max_good_mae = default_thresholds(symbol)

        if direction == "NEUTRAL":
            result_label = "PENDING_DIRECTIONAL_CONFIRMATION"
        elif not candles:
            result_label = "PENDING_NO_DATA"
        else:
            result_label = classify_outcome(
                mfe_30m=mfe_30m,
                mae_30m=mae_30m,
                min_good_mfe=min_good_mfe,
                max_good_mae=max_good_mae,
            )

        base_record.update(
            {
                "price_after_15m": price_after_15m,
                "price_after_30m": price_after_30m,
                "price_after_60m": price_after_60m,
                "mfe_15m": mfe_15m,
                "mae_15m": mae_15m,
                "mfe_30m": mfe_30m,
                "mae_30m": mae_30m,
                "mfe_60m": mfe_60m,
                "mae_60m": mae_60m,
                "result_label": result_label,
                "raw_result": {
                    "min_good_mfe": min_good_mfe,
                    "max_good_mae": max_good_mae,
                    "candle_count": len(candles),
                    "direction": direction,
                },
            }
        )
        return base_record


# Legacy placeholder kept for backwards compatibility.
async def track_outcome(trade_plan_id: int, symbol: str) -> None:  # pragma: no cover
    return None
