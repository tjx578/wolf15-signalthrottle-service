from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.storage.repositories import SignalRepository

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/dashboard/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    try:
        repo = SignalRepository()
        active_blocks = await repo.get_active_blocks()
        latest_signals = await repo.get_latest_trade_plans(limit=20)
        stats = await repo.get_dashboard_stats()
    except Exception as exc:
        logger.warning("Dashboard DB query failed: %s", exc)
        active_blocks = []
        latest_signals = []
        stats = {
            "active_blocks": 0,
            "priority_signals": 0,
            "avg_density": "0.0",
            "last_update": "-",
        }

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "active_blocks": active_blocks,
            "latest_signals": latest_signals,
            "stats": stats,
        },
    )


@router.get("/signals/{signal_id}", response_class=HTMLResponse)
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
