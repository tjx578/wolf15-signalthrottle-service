from __future__ import annotations

import logging
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .auth import require_dashboard_auth
from ..config import settings
from ..dashboard.view_models import build_active_block_view, build_trade_signal_view
from ..ingestion.engine_log_sync import owner_day_window_utc
from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_dashboard_auth)])
templates = Jinja2Templates(directory="app/dashboard/templates")


async def _load_section(loader, fallback, section_name: str, section_errors: list[dict[str, str]]):
    try:
        return await loader()
    except Exception as exc:
        logger.warning("Dashboard section %s failed: %s", section_name, exc)
        section_errors.append(
            {
                "section": section_name,
                "message": str(exc),
            }
        )
        return fallback


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    repo = SignalRepository()
    section_errors: list[dict[str, str]] = []
    active_blocks = await _load_section(
        lambda: repo.get_active_blocks(),
        [],
        "active_blocks",
        section_errors,
    )
    radar_signals = await _load_section(
        lambda: repo.get_latest_signals(limit=12, bucket="radar"),
        [],
        "radar_signals",
        section_errors,
    )
    failed_signals = await _load_section(
        lambda: repo.get_latest_signals(limit=12, bucket="failed"),
        [],
        "failed_signals",
        section_errors,
    )
    watchlist_signals = await _load_section(
        lambda: repo.get_latest_signals(limit=12, bucket="watchlist"),
        [],
        "watchlist_signals",
        section_errors,
    )
    ready_trade_plans = await _load_section(
        lambda: repo.get_latest_signals(limit=12, bucket="ready"),
        [],
        "ready_trade_plans",
        section_errors,
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
        section_errors,
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
            "best_h4_context_type": None,
            "worst_h4_context_type": None,
        },
        "outcome_summary",
        section_errors,
    )
    outcomes_by_phase = await _load_section(
        lambda: repo.get_outcomes_by_phase(),
        [],
        "outcomes_by_phase",
        section_errors,
    )
    outcomes_by_h4_context = await _load_section(
        lambda: repo.get_outcomes_by_h4_context_type(),
        [],
        "outcomes_by_h4_context",
        section_errors,
    )
    outcomes_by_reason_code = await _load_section(
        lambda: repo.get_outcomes_by_reason_code(),
        [],
        "outcomes_by_reason_code",
        section_errors,
    )
    outcomes_by_grade = await _load_section(
        lambda: repo.get_outcomes_by_grade(),
        [],
        "outcomes_by_grade",
        section_errors,
    )
    latest_outcomes = await _load_section(
        lambda: repo.get_latest_outcomes(limit=12),
        [],
        "latest_outcomes",
        section_errors,
    )

    active_blocks = [build_active_block_view(row) for row in active_blocks]
    radar_signals = [build_trade_signal_view(row) for row in radar_signals]
    failed_signals = [build_trade_signal_view(row) for row in failed_signals]
    watchlist_signals = [build_trade_signal_view(row) for row in watchlist_signals]
    ready_trade_plans = [build_trade_signal_view(row) for row in ready_trade_plans]

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "active_blocks": active_blocks,
            "radar_signals": radar_signals,
            "failed_signals": failed_signals,
            "watchlist_signals": watchlist_signals,
            "ready_trade_plans": ready_trade_plans,
            "stats": stats,
            "outcome_summary": outcome_summary,
            "outcomes_by_phase": outcomes_by_phase,
            "outcomes_by_h4_context": outcomes_by_h4_context,
            "outcomes_by_reason_code": outcomes_by_reason_code,
            "outcomes_by_grade": outcomes_by_grade,
            "latest_outcomes": latest_outcomes,
            "section_errors": section_errors,
        },
    )


@router.get("/signal-detail/{signal_id}", response_class=HTMLResponse)
async def signal_detail_page(request: Request, signal_id: int):
    repo = SignalRepository()
    signal = await repo.get_trade_plan(signal_id)

    return templates.TemplateResponse(
        request,
        "signal_detail.html",
        {
            "signal": build_trade_signal_view(signal),
        },
    )


@router.get("/series-detail/{symbol}", response_class=HTMLResponse)
async def series_detail_page(request: Request, symbol: str):
    repo = SignalRepository()
    detail = await repo.get_signal_series_detail(symbol)

    return templates.TemplateResponse(
        request,
        "series_detail.html",
        {
            "detail": detail,
            "symbol": symbol,
        },
    )


@router.get("/engine-logs/daily", response_class=HTMLResponse)
async def engine_logs_daily_page(request: Request, date: str | None = None):
    repo = SignalRepository()
    if date:
        day = datetime.fromisoformat(date).date()
        owner_now = datetime.combine(day, time.max, tzinfo=timezone.utc)
    else:
        owner_now = datetime.now(timezone.utc)

    start_utc, end_utc = owner_day_window_utc(owner_now, settings.owner_timezone)
    summary = await repo.get_engine_logs_daily_summary(start_utc=start_utc, end_utc=end_utc)

    return templates.TemplateResponse(
        request,
        "engine_logs_daily.html",
        {
            "summary": summary,
            "selected_date": date or owner_now.date().isoformat(),
            "window": {
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
                "owner_timezone": settings.owner_timezone,
            },
        },
    )
