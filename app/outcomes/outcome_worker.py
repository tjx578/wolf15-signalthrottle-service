"""Outcome worker — Phase 4.

Periodically scans trade plans without an outcome record, evaluates
those that are at least ~65 minutes past their signal_end_utc, and
upserts the resulting MFE/MAE/label snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.config import settings
from app.market.finnhub_client import FinnhubClient
from app.outcomes.mfe_mae_tracker import MFEMAETracker, _coerce_datetime
from app.storage.repositories import SignalRepository


DEFAULT_DUE_SECONDS = 65 * 60


class OutcomeWorker:
    def __init__(self, repo: SignalRepository | None = None) -> None:
        self.repo = repo or SignalRepository()

    async def process_due_outcomes(self, limit: int = 20) -> dict[str, int]:
        stats = {"considered": 0, "processed": 0, "skipped": 0, "errors": 0}

        if not settings.finnhub_api_key:
            logger.debug("Outcome worker skipped: FINNHUB_API_KEY not configured")
            return stats

        due_plans = await self.repo.get_trade_plans_without_outcome(limit=limit)
        if not due_plans:
            return stats

        client = FinnhubClient(api_key=settings.finnhub_api_key)
        tracker = MFEMAETracker(client)

        for plan in due_plans:
            stats["considered"] += 1
            try:
                if not self._is_due(plan):
                    stats["skipped"] += 1
                    continue

                result = await tracker.evaluate(plan)
                await self.repo.upsert_signal_outcome(plan["id"], result)
                stats["processed"] += 1

                logger.info(
                    "Outcome calculated trade_plan_id={} symbol={} label={}",
                    plan["id"],
                    plan.get("symbol"),
                    result.get("result_label"),
                )
            except Exception as exc:
                stats["errors"] += 1
                logger.exception(
                    "Outcome calculation failed trade_plan_id={}: {}",
                    plan.get("id"),
                    exc,
                )
        return stats

    def _is_due(self, plan: dict[str, Any]) -> bool:
        payload = plan.get("payload") or {}
        signal_end_utc = (
            _coerce_datetime(payload.get("signal_end_utc"))
            or _coerce_datetime(plan.get("signal_end_utc"))
            or _coerce_datetime(plan.get("created_at"))
        )
        if signal_end_utc is None:
            return False

        now = datetime.now(timezone.utc)
        return (now - signal_end_utc).total_seconds() >= DEFAULT_DUE_SECONDS
