from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/dashboard/templates")


async def _load_section(loader, fallback, section_name: str):
    try:
        return await loader()
    except Exception as exc:
        logger.warning("Dashboard section %s failed: %s", section_name, exc)
        return fallback


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    repo = SignalRepository()
    active_blocks = await _load_section(
        lambda: repo.get_active_blocks(),
        [],
        "active_blocks",
    )
    priority_trade_plans = await _load_section(
        lambda: repo.get_latest_signals(limit=12, bucket="priority"),
        [],
        "priority_trade_plans",
    )
    actionable_trade_plans = await _load_section(
        lambda: repo.get_latest_signals(limit=12, bucket="actionable"),
        [],
        "actionable_trade_plans",
    )
    watchlist_signals = await _load_section(
        lambda: repo.get_latest_signals(limit=12, bucket="watchlist"),
        [],
        "watchlist_signals",
    )
    stats = await _load_section(
        lambda: repo.get_dashboard_stats(),
        {
            "active_blocks": 0,
            "priority_signals": 0,
            "avg_density": "0.0",
            "last_update": "-",
        },
        "stats",
    )
    outcome_summary = await _load_section(
        lambda: repo.get_outcome_summary(),
        {
            "total": 0,
            "strong_pct": 0,
            "avg_mfe_30m": 0,
            "avg_mae_30m": 0,
            "best_phase": None,
            "worst_phase": None,
        },
        "outcome_summary",
    )
    outcomes_by_phase = await _load_section(
        lambda: repo.get_outcomes_by_phase(),
        [],
        "outcomes_by_phase",
    )
    outcomes_by_grade = await _load_section(
        lambda: repo.get_outcomes_by_grade(),
        [],
        "outcomes_by_grade",
    )
    latest_outcomes = await _load_section(
        lambda: repo.get_latest_outcomes(limit=12),
        [],
        "latest_outcomes",
    )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "active_blocks": active_blocks,
            "priority_trade_plans": priority_trade_plans,
            "actionable_trade_plans": actionable_trade_plans,
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
