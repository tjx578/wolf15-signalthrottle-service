from __future__ import annotations

import logging
from typing import Any

from ..config import settings
from ..market.finnhub_client import FinnhubClient
from ..market.market_snapshot_builder import MarketSnapshotBuilder
from .trade_plan_builder import build_trade_plan
from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)

ELIGIBLE_GRADES = {"B+", "A-", "A", "A+"}


async def enrich_block_with_market_context(
    block: dict[str, Any],
    repo: SignalRepository | None = None,
) -> dict[str, Any] | None:
    if not settings.enable_market_context:
        return None

    if block["pressure_grade"] not in ELIGIBLE_GRADES:
        return None

    if not settings.finnhub_api_key:
        return None

    repository = repo or SignalRepository()
    block_id = block.get("id")
    if block_id is None:
        return None

    existing = await repository.get_trade_plan_for_block(block_id)
    if existing:
        return existing

    client = FinnhubClient(api_key=settings.finnhub_api_key)
    snapshot_builder = MarketSnapshotBuilder(client)

    try:
        snapshot = await snapshot_builder.build(block)

        # Extract only fields for market_snapshots table
        market_snapshot_data = {
            "block_id": snapshot.get("block_id"),
            "symbol": snapshot["symbol"],
            "signal_start_utc": snapshot.get("signal_start_utc"),
            "signal_end_utc": snapshot.get("signal_end_utc"),
            "price_at_start": snapshot.get("price_at_start"),
            "price_at_end": snapshot.get("price_at_end"),
            "spread_points": snapshot.get("spread_points"),
            "d1_bias": snapshot.get("d1_bias"),
            "h4_structure": snapshot.get("h4_structure"),
            "h1_phase": snapshot.get("h1_phase"),
            "m15_phase": snapshot.get("m15_phase"),
            "chart_bias": snapshot.get("chart_bias"),
            "chart_phase": snapshot.get("chart_phase"),
            "support_zone": snapshot.get("support_zone"),
            "resistance_zone": snapshot.get("resistance_zone"),
            "key_level": snapshot.get("key_level"),
            "raw_ohlc": snapshot.get("raw_ohlc"),
        }

        snapshot_id = await repository.insert_market_snapshot(market_snapshot_data)

        # Pass full snapshot (with phase fields) to build_trade_plan
        trade_plan = build_trade_plan(block, snapshot)
        trade_plan["block_id"] = block_id
        trade_plan["market_snapshot_id"] = snapshot_id
        trade_plan_id = await repository.insert_trade_plan(block_id, trade_plan)
        trade_plan["id"] = trade_plan_id
        return trade_plan
    except Exception as exc:
        logger.warning("Market context enrichment failed for block %s: %s", block_id, exc)
        return None