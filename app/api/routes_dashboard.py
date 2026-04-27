from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/dashboard/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    try:
        repo = SignalRepository()
        active_blocks = await repo.get_active_blocks()
        latest_signals = await repo.get_latest_trade_plans(limit=12, bucket="actionable")
        watchlist_signals = await repo.get_latest_trade_plans(limit=12, bucket="watchlist")
        stats = await repo.get_dashboard_stats()
        outcome_summary = await repo.get_outcome_summary()
        outcomes_by_phase = await repo.get_outcomes_by_phase()
        outcomes_by_grade = await repo.get_outcomes_by_grade()
        latest_outcomes = await repo.get_latest_outcomes(limit=12)
    except Exception as exc:
        logger.warning("Dashboard DB query failed: %s", exc)
        active_blocks = []
        latest_signals = []
        watchlist_signals = []
        stats = {
            "active_blocks": 0,
            "priority_signals": 0,
            "avg_density": "0.0",
            "last_update": "-",
        }
        outcome_summary = {
            "total": 0,
            "strong_pct": 0,
            "avg_mfe_30m": 0,
            "avg_mae_30m": 0,
            "best_phase": None,
            "worst_phase": None,
        }
        outcomes_by_phase = []
        outcomes_by_grade = []
        latest_outcomes = []

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "active_blocks": active_blocks,
            "latest_signals": latest_signals,
            "watchlist_signals": watchlist_signals,
            "stats": stats,
            "outcome_summary": outcome_summary,
            "outcomes_by_phase": outcomes_by_phase,
            "outcomes_by_grade": outcomes_by_grade,
            "latest_outcomes": latest_outcomes,
        },
    )


@router.get("/signal-detail/{signal_id}", response_class=HTMLResponse)
async def signal_detail_page(request: Request, signal_id: int):
    repo = SignalRepository()
    signal = await repo.get_trade_plan(signal_id)

    return templates.TemplateResponse(
        "signal_detail.html",
        {
            "request": request,
            "signal": signal,
        },
    )
