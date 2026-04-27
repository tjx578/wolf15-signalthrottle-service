from __future__ import annotations

import logging
from typing import Any, cast

from ..config import settings
from ..market.finnhub_client import FinnhubClient
from ..market.market_snapshot_builder import MarketSnapshotBuilder
from ..storage.repository_protocols import (
    MarketContextRepository,
    MarketContextWriteRepository,
)
from .trade_plan_builder import build_trade_plan
from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)

ELIGIBLE_GRADES = {"B+", "A-", "A", "A+"}


async def enrich_block_with_market_context(
    block: dict[str, Any],
    repo: MarketContextRepository | None = None,
) -> dict[str, Any] | None:
    repository = repo or SignalRepository()
    block_id = block.get("id")
    pressure_grade = block["pressure_grade"]
    eligible = pressure_grade in ELIGIBLE_GRADES

    async def _mark(
        market_context_status: str,
        trade_plan_status: str,
        pending_reason: str | None = None,
    ) -> None:
        if block_id is None:
            return
        try:
            await repository.mark_block_market_context_status(
                block_id,
                market_context_status=market_context_status,
                trade_plan_status=trade_plan_status,
                pending_reason=pending_reason,
            )
        except Exception:
            # Don't let the audit write itself swallow a real enrichment.
            logger.exception(
                "Failed to persist market_context_status for block %s", block_id
            )

    if not settings.enable_market_context:
        if eligible:
            await _mark("DISABLED", "PENDING_MARKET_CONTEXT", "MARKET_CONTEXT_DISABLED")
        return None

    if not eligible:
        await _mark("NOT_REQUESTED", "NOT_REQUIRED")
        return None

    if not settings.finnhub_api_key:
        await _mark(
            "FINNHUB_KEY_MISSING",
            "PENDING_MARKET_CONTEXT",
            "FINNHUB_API_KEY_MISSING",
        )
        return None

    if block_id is None:
        return None

    existing = await repository.get_trade_plan_for_block(block_id)
    if existing:
        await _mark("READY", "READY")
        return existing

    client = FinnhubClient(api_key=settings.finnhub_api_key)
    snapshot_builder = MarketSnapshotBuilder(client)
    write_repository = cast(MarketContextWriteRepository, repository)

    try:
        snapshot = await snapshot_builder.build(block)
        snapshot_id = await write_repository.insert_market_snapshot(snapshot)
        trade_plan = build_trade_plan(block, snapshot)
        trade_plan["block_id"] = block_id
        trade_plan["market_snapshot_id"] = snapshot_id
        trade_plan_id = await write_repository.insert_trade_plan(block_id, trade_plan)
        trade_plan["id"] = trade_plan_id
        await _mark("READY", "READY")
        return trade_plan
    except Exception as exc:
        logger.warning(
            "Market context enrichment failed for block %s: %s", block_id, exc
        )
        await _mark(
            "OHLC_FETCH_FAILED",
            "PENDING_MARKET_CONTEXT",
            f"OHLC_FETCH_FAILED: {exc}"[:500],
        )
        return None