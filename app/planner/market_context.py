from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.market.finnhub_client import FinnhubClient
from app.market.market_snapshot_builder import MarketSnapshotBuilder
from app.planner.trade_plan_builder import build_trade_plan
from app.storage.repositories import SignalRepository

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
        snapshot_id = await repository.insert_market_snapshot(snapshot)
        trade_plan = build_trade_plan(block, snapshot)
        trade_plan["block_id"] = block_id
        trade_plan["market_snapshot_id"] = snapshot_id
        trade_plan["payload"] = trade_plan.get("raw", {})
        trade_plan_id = await repository.insert_trade_plan(block_id, trade_plan)
        trade_plan["id"] = trade_plan_id
        return trade_plan
    except Exception as exc:
        logger.warning("Market context enrichment failed for block %s: %s", block_id, exc)
        return None