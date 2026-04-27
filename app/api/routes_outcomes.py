from __future__ import annotations

import logging

from fastapi import APIRouter

from ..outcomes.outcome_worker import OutcomeWorker
from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/latest")
async def latest_outcomes(limit: int = 20):
    repo = SignalRepository()
    rows = await repo.get_latest_outcomes(limit=limit)
    return {"count": len(rows), "outcomes": rows}


@router.get("/summary")
async def outcome_summary():
    repo = SignalRepository()
    return await repo.get_outcome_summary()


@router.get("/by-phase")
async def outcomes_by_phase():
    repo = SignalRepository()
    rows = await repo.get_outcomes_by_phase()
    return {"count": len(rows), "rows": rows}


@router.get("/by-grade")
async def outcomes_by_grade():
    repo = SignalRepository()
    rows = await repo.get_outcomes_by_grade()
    return {"count": len(rows), "rows": rows}


@router.post("/backfill")
async def backfill_outcomes(limit: int = 50):
    worker = OutcomeWorker()
    stats = await worker.process_due_outcomes(limit=limit)
    return {"status": "processed", "stats": stats}
