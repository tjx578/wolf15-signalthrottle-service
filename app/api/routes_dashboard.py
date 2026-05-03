from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .auth import require_dashboard_auth
from ..config import settings
from ..dashboard.view_models import build_active_block_view, build_trade_signal_view
from ..ingestion.engine_log_sync import utc_day_bounds
from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_dashboard_auth)])
templates = Jinja2Templates(directory="app/dashboard/templates")

DashboardLoader = Callable[[SignalRepository], Awaitable[Any]]
DashboardTransform = Callable[[Any], Any]


def _trade_signal_views(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [build_trade_signal_view(row) for row in rows]


SECTION_SPECS: dict[str, dict[str, Any]] = {
    "stats": {
        "loader": lambda repo: repo.get_dashboard_stats(),
        "fallback": {
            "active_blocks": 0,
            "priority_signals": 0,
            "avg_density": "0.0",
            "last_update": "-",
        },
        "context_key": "stats",
        "template": "partials/dashboard_stats.html",
    },
    "active_blocks": {
        "loader": lambda repo: repo.get_active_blocks(),
        "fallback": [],
        "context_key": "active_blocks",
        "template": "partials/active_blocks.html",
        "transform": lambda rows: [build_active_block_view(row) for row in rows],
    },
    "radar_signals": {
        "loader": lambda repo: repo.get_latest_signals(limit=12, bucket="radar"),
        "fallback": [],
        "context_key": "radar_signals",
        "template": "partials/radar_signals.html",
        "transform": _trade_signal_views,
    },
    "failed_signals": {
        "loader": lambda repo: repo.get_latest_signals(limit=12, bucket="failed"),
        "fallback": [],
        "context_key": "failed_signals",
        "template": "partials/failed_signals.html",
        "transform": _trade_signal_views,
    },
    "watchlist_signals": {
        "loader": lambda repo: repo.get_latest_signals(limit=12, bucket="watchlist"),
        "fallback": [],
        "context_key": "watchlist_signals",
        "template": "partials/watchlist_signals.html",
        "transform": _trade_signal_views,
    },
    "ready_trade_plans": {
        "loader": lambda repo: repo.get_latest_signals(limit=12, bucket="ready"),
        "fallback": [],
        "context_key": "ready_trade_plans",
        "template": "partials/ready_trade_plans.html",
        "transform": _trade_signal_views,
    },
    "outcome_summary": {
        "loader": lambda repo: repo.get_outcome_summary(),
        "fallback": {
            "total": 0,
            "strong_pct": 0,
            "avg_mfe_30m": 0,
            "avg_mae_30m": 0,
            "best_phase": None,
            "worst_phase": None,
            "best_h4_context_type": None,
            "worst_h4_context_type": None,
        },
        "context_key": "outcome_summary",
        "template": "partials/outcome_summary.html",
    },
    "outcomes_by_phase": {
        "loader": lambda repo: repo.get_outcomes_by_phase(),
        "fallback": [],
        "context_key": "outcomes_by_phase",
        "template": "partials/outcomes_by_phase.html",
    },
    "outcomes_by_grade": {
        "loader": lambda repo: repo.get_outcomes_by_grade(),
        "fallback": [],
        "context_key": "outcomes_by_grade",
        "template": "partials/outcomes_by_grade.html",
    },
    "outcomes_by_h4_context": {
        "loader": lambda repo: repo.get_outcomes_by_h4_context_type(),
        "fallback": [],
        "context_key": "outcomes_by_h4_context",
        "template": "partials/outcomes_by_h4_context.html",
    },
    "outcomes_by_reason_code": {
        "loader": lambda repo: repo.get_outcomes_by_reason_code(),
        "fallback": [],
        "context_key": "outcomes_by_reason_code",
        "template": "partials/outcomes_by_reason_code.html",
    },
    "latest_outcomes": {
        "loader": lambda repo: repo.get_latest_outcomes(limit=12),
        "fallback": [],
        "context_key": "latest_outcomes",
        "template": "partials/latest_outcomes.html",
    },
}

HOME_SECTION_ORDER = [
    "stats",
    "active_blocks",
    "radar_signals",
    "failed_signals",
    "watchlist_signals",
    "ready_trade_plans",
    "outcome_summary",
    "outcomes_by_phase",
    "outcomes_by_grade",
    "outcomes_by_h4_context",
    "outcomes_by_reason_code",
    "latest_outcomes",
]

PHASE2_DASHBOARD_SECTIONS = {
    "ready_trade_plans",
    "outcome_summary",
    "outcomes_by_phase",
    "outcomes_by_grade",
    "outcomes_by_h4_context",
    "outcomes_by_reason_code",
    "latest_outcomes",
}


def _phase1_mode() -> bool:
    return settings.signalthrottle_mode.lower() == "phase1"


def _home_section_order() -> list[str]:
    if not _phase1_mode():
        return HOME_SECTION_ORDER
    return [
        section_name
        for section_name in HOME_SECTION_ORDER
        if section_name not in PHASE2_DASHBOARD_SECTIONS
    ]


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


async def _load_dashboard_fragment_context(
    repo: SignalRepository,
    section_name: str,
) -> tuple[str, dict[str, Any]]:
    spec = SECTION_SPECS.get(section_name)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown dashboard section: {section_name}")

    section_errors: list[dict[str, str]] = []
    loader: DashboardLoader = spec["loader"]
    value = await _load_section(
        lambda: loader(repo),
        spec["fallback"],
        section_name,
        section_errors,
    )
    transform: DashboardTransform | None = spec.get("transform")
    if transform is not None:
        value = transform(value)

    return spec["template"], {
        spec["context_key"]: value,
        "section_error": section_errors[0] if section_errors else None,
        "phase1_mode": _phase1_mode(),
    }


async def _load_dashboard_home_context(repo: SignalRepository) -> dict[str, Any]:
    context: dict[str, Any] = {}
    section_errors: list[dict[str, str]] = []

    for section_name in _home_section_order():
        _, fragment_context = await _load_dashboard_fragment_context(repo, section_name)
        context.update({k: v for k, v in fragment_context.items() if k != "section_error"})
        if fragment_context.get("section_error"):
            section_errors.append(fragment_context["section_error"])

    context["section_errors"] = section_errors
    context["phase1_mode"] = _phase1_mode()
    return context


async def _load_engine_logs_daily_context(date: str | None) -> dict[str, Any]:
    repo = SignalRepository()
    if date:
        day = datetime.fromisoformat(date).date()
    else:
        day = datetime.now(timezone.utc).date()

    start_utc, end_utc = utc_day_bounds(day)
    summary = await repo.get_engine_logs_daily_summary(start_utc=start_utc, end_utc=end_utc)
    return {
        "summary": summary,
        "selected_date": day.isoformat(),
        "window": {
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "window_rule": "[start_utc, end_utc)",
            "owner_timezone": settings.owner_timezone,
        },
        "section_error": None,
        "phase1_mode": _phase1_mode(),
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    repo = SignalRepository()
    context = await _load_dashboard_home_context(repo)

    return templates.TemplateResponse(
        request,
        "index.html",
        context,
    )


@router.get("/partials/{section_name}", response_class=HTMLResponse)
async def dashboard_section_partial(request: Request, section_name: str):
    repo = SignalRepository()
    template_name, context = await _load_dashboard_fragment_context(repo, section_name)
    return templates.TemplateResponse(request, template_name, context)


@router.get("/signal-detail/{signal_id}", response_class=HTMLResponse)
async def signal_detail_page(request: Request, signal_id: int):
    repo = SignalRepository()
    signal = await repo.get_trade_plan(signal_id)

    return templates.TemplateResponse(
        request,
        "signal_detail.html",
        {
            "signal": build_trade_signal_view(signal),
            "phase1_mode": _phase1_mode(),
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
            "phase1_mode": _phase1_mode(),
        },
    )


@router.get("/engine-logs/daily", response_class=HTMLResponse)
async def engine_logs_daily_page(request: Request, date: str | None = None):
    context = await _load_engine_logs_daily_context(date)

    return templates.TemplateResponse(
        request,
        "engine_logs_daily.html",
        context,
    )


@router.get("/partials/engine-logs/daily", response_class=HTMLResponse)
async def engine_logs_daily_partial(request: Request, date: str | None = None):
    context = await _load_engine_logs_daily_context(date)
    return templates.TemplateResponse(request, "_engine_logs_daily_fragment.html", context)
