from __future__ import annotations

import logging
from typing import Any, cast

from ..config import settings
from ..detector.block_relation import classify_block_relation
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


async def _attach_chain_context(
    block: dict[str, Any],
    repository: MarketContextRepository,
) -> dict[str, Any]:
    symbol = block.get("symbol")
    start_utc = block.get("start_utc")
    if not symbol or start_utc is None:
        return block

    previous = await repository.get_previous_block_before(
        symbol,
        start_utc,
        exclude_block_id=block.get("id"),
    )
    if not previous:
        return {
            **block,
            "block_relation": block.get("block_relation") or "FIRST_BLOCK",
        }

    previous_end_utc = previous.get("end_utc")
    gap_minutes: float | None = None
    if previous_end_utc is not None:
        gap_minutes = round((start_utc - previous_end_utc).total_seconds() / 60.0, 2)

    relation = classify_block_relation(gap_minutes, previous.get("pressure_grade"))
    chain_context = {
        "previous_block_id": previous.get("id"),
        "previous_block_grade": previous.get("pressure_grade"),
        "previous_block_end_wita": previous.get("end_wita"),
        "gap_from_previous_minutes": gap_minutes,
        "relation": relation,
    }
    return {
        **block,
        "previous_block_id": block.get("previous_block_id") or previous.get("id"),
        "previous_block_grade": previous.get("pressure_grade"),
        "previous_block_end_wita": previous.get("end_wita"),
        "gap_from_previous_minutes": gap_minutes,
        "block_relation": relation,
        "chain_context": chain_context,
    }


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

    if not settings.enable_trade_plans:
        if eligible:
            await _mark("DISABLED", "NOT_REQUIRED", "TRADE_PLANS_DISABLED_PHASE1")
        return None

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

    block = await _attach_chain_context(block, repository)

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
