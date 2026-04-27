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


@router.get("/by-h4-context")
async def outcomes_by_h4_context():
    repo = SignalRepository()
    rows = await repo.get_outcomes_by_h4_context_type()
    return {"count": len(rows), "rows": rows}


@router.get("/by-reason-code")
async def outcomes_by_reason_code():
    repo = SignalRepository()
    rows = await repo.get_outcomes_by_reason_code()
    return {"count": len(rows), "rows": rows}


@router.post("/backfill")
async def backfill_outcomes(limit: int = 50):
    worker = OutcomeWorker()
    stats = await worker.process_due_outcomes(limit=limit)
    return {"status": "processed", "stats": stats}


# IMPORTANT: keep dynamic /{outcome_id} route LAST so it does not swallow
# /latest, /summary, /by-phase, /by-grade, /by-h4-context,
# /by-reason-code, /backfill.
@router.get("/{outcome_id}")
async def outcome_detail(outcome_id: int):
    repo = SignalRepository()
    row = await repo.get_outcome(outcome_id)
    if not row:
        return {"status": "not_found", "outcome_id": outcome_id}
    return row
