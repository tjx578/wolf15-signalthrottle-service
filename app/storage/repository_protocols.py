from __future__ import annotations

from typing import Any, Protocol


class MarketContextRepository(Protocol):
    async def mark_block_market_context_status(
        self,
        block_id: int,
        *,
        market_context_status: str,
        trade_plan_status: str,
        pending_reason: str | None = None,
    ) -> None:
        ...

    async def get_trade_plan_for_block(self, block_id: int) -> dict[str, Any] | None:
        ...

    async def get_previous_block_before(
        self,
        symbol: str,
        start_utc: Any,
        *,
        exclude_block_id: int | None = None,
    ) -> dict[str, Any] | None:
        ...


class MarketContextWriteRepository(MarketContextRepository, Protocol):

    async def insert_market_snapshot(self, snapshot: dict[str, Any]) -> int:
        ...

    async def insert_trade_plan(self, block_id: int, plan: dict[str, Any]) -> int:
        ...


class FinalizerRepository(MarketContextWriteRepository, Protocol):
    async def get_active_or_cooling_blocks(self) -> list[dict[str, Any]]:
        ...

    async def mark_block_cooling(self, block_id: int) -> None:
        ...

    async def mark_block_soft_finalized(self, block_id: int) -> None:
        ...

    async def mark_block_hard_finalized(self, block_id: int) -> None:
        ...


class OutcomeWorkerRepository(Protocol):
    async def get_trade_plans_without_outcome(self, limit: int = 20) -> list[dict[str, Any]]:
        ...

    async def upsert_signal_outcome(
        self,
        trade_plan_id: int,
        result: dict[str, Any],
    ) -> int:
        ...