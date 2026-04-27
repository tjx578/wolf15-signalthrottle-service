"""Tests for market_context enrichment status persistence.

The enricher MUST always record what happened on the block via
`mark_block_market_context_status`, so the dashboard can surface a real
pending_reason instead of a silent dash. These tests verify the major
code paths: missing Finnhub key, market context disabled, and ineligible
grade.
"""
from __future__ import annotations

import asyncio
from typing import Any

import app.planner.market_context as market_context_module
from app.planner.market_context import enrich_block_with_market_context


class FakeRepo:
    def __init__(self) -> None:
        self.marks: list[dict[str, Any]] = []
        self.trade_plan_for_block: dict | None = None

    async def mark_block_market_context_status(
        self,
        block_id: int,
        *,
        market_context_status: str,
        trade_plan_status: str,
        pending_reason: str | None = None,
    ) -> None:
        self.marks.append(
            {
                "block_id": block_id,
                "market_context_status": market_context_status,
                "trade_plan_status": trade_plan_status,
                "pending_reason": pending_reason,
            }
        )

    async def get_trade_plan_for_block(self, block_id: int):
        return self.trade_plan_for_block


def test_enrich_records_finnhub_key_missing(monkeypatch) -> None:
    """B+ block + missing API key must persist FINNHUB_KEY_MISSING with
    a human-readable pending_reason and PENDING_MARKET_CONTEXT trade plan
    status. This is the dashboard contract: never a silent dash."""
    monkeypatch.setattr(market_context_module.settings, "enable_market_context", True)
    monkeypatch.setattr(market_context_module.settings, "finnhub_api_key", "")

    repo = FakeRepo()
    block = {"id": 11, "symbol": "USDJPY", "pressure_grade": "B+"}

    result = asyncio.run(enrich_block_with_market_context(block, repo=repo))

    assert result is None
    assert len(repo.marks) == 1
    mark = repo.marks[0]
    assert mark["block_id"] == 11
    assert mark["market_context_status"] == "FINNHUB_KEY_MISSING"
    assert mark["trade_plan_status"] == "PENDING_MARKET_CONTEXT"
    assert mark["pending_reason"] == "FINNHUB_API_KEY_MISSING"


def test_enrich_records_disabled(monkeypatch) -> None:
    """When market context is globally disabled, an eligible block still
    needs an audit row so the dashboard knows the pending reason."""
    monkeypatch.setattr(market_context_module.settings, "enable_market_context", False)

    repo = FakeRepo()
    block = {"id": 22, "symbol": "EURUSD", "pressure_grade": "A"}

    result = asyncio.run(enrich_block_with_market_context(block, repo=repo))

    assert result is None
    assert repo.marks == [
        {
            "block_id": 22,
            "market_context_status": "DISABLED",
            "trade_plan_status": "PENDING_MARKET_CONTEXT",
            "pending_reason": "MARKET_CONTEXT_DISABLED",
        }
    ]


def test_enrich_marks_ineligible_grade_as_not_requested(monkeypatch) -> None:
    """A C-grade block is below threshold; the audit row should declare
    NOT_REQUESTED / NOT_REQUIRED so the dashboard never shows it as
    pending."""
    monkeypatch.setattr(market_context_module.settings, "enable_market_context", True)
    monkeypatch.setattr(market_context_module.settings, "finnhub_api_key", "x")

    repo = FakeRepo()
    block = {"id": 33, "symbol": "GBPUSD", "pressure_grade": "C"}

    result = asyncio.run(enrich_block_with_market_context(block, repo=repo))

    assert result is None
    assert repo.marks == [
        {
            "block_id": 33,
            "market_context_status": "NOT_REQUESTED",
            "trade_plan_status": "NOT_REQUIRED",
            "pending_reason": None,
        }
    ]
