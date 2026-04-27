from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import settings
from app.planner.market_context import enrich_block_with_market_context
from app.storage.repository_protocols import FinalizerRepository
from app.storage.repositories import SignalRepository

logger = logging.getLogger(__name__)


def determine_finalize_mode(
    last_event_utc: datetime,
    now_utc: datetime | None = None,
    soft_seconds: int = 90,
    hard_seconds: int = 300,
) -> str:
    """Return the finalize mode based on silence duration.

    - ACTIVE: still receiving events (gap < soft_seconds)
    - COOLING: between soft and hard threshold
    - SOFT_FINALIZED: past soft but before hard
    - HARD_FINALIZED: past hard threshold
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    gap = (now_utc - last_event_utc).total_seconds()

    if gap < 30:
        return "ACTIVE"
    if gap < soft_seconds:
        return "COOLING"
    if gap < hard_seconds:
        return "SOFT_FINALIZED"
    return "HARD_FINALIZED"


class SignalFinalizer:
    def __init__(self, repo: FinalizerRepository | None = None) -> None:
        self.repo = repo or SignalRepository()

    async def finalize_due_blocks(self, now_utc: datetime | None = None) -> None:
        current_time = now_utc or datetime.now(timezone.utc)
        active_blocks = await self.repo.get_active_or_cooling_blocks()

        for block in active_blocks:
            last_event_utc = block.get("last_event_utc") or block["end_utc"]
            mode = determine_finalize_mode(
                last_event_utc=last_event_utc,
                now_utc=current_time,
                soft_seconds=settings.soft_finalize_seconds,
                hard_seconds=settings.hard_finalize_seconds,
            )

            if mode == "COOLING" and block.get("pressure_status") == "ACTIVE":
                await self.repo.mark_block_cooling(block["id"])
                continue

            if mode == "SOFT_FINALIZED":
                await self._soft_finalize(block)
                continue

            if mode == "HARD_FINALIZED":
                await self._hard_finalize(block)

    async def _soft_finalize(self, block: dict) -> None:
        if block.get("pressure_status") in {"SOFT_FINALIZED", "HARD_FINALIZED"}:
            return

        logger.info("Soft finalizing block id=%s symbol=%s", block["id"], block["symbol"])
        await self.repo.mark_block_soft_finalized(block["id"])

        finalized_block = {
            **block,
            "pressure_status": "SOFT_FINALIZED",
            "finalize_mode": "SOFT_FINALIZED",
            "is_active": False,
        }
        trade_plan = await enrich_block_with_market_context(finalized_block, self.repo)
        if trade_plan:
            logger.info(
                "Trade plan created block_id=%s symbol=%s",
                block["id"],
                block["symbol"],
            )

    async def _hard_finalize(self, block: dict) -> None:
        if block.get("pressure_status") == "HARD_FINALIZED":
            return

        logger.info("Hard finalizing block id=%s symbol=%s", block["id"], block["symbol"])
        await self.repo.mark_block_hard_finalized(block["id"])
