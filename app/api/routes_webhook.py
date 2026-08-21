from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..models.log_event import LogEvent
from ..parser.signalthrottle_parser import parse_signalthrottle
from ..parser.timestamp_mapper import to_chart_time, to_wita
from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)
router = APIRouter()


class SignalThrottleWebhookPayload(BaseModel):
    event: str = "signal_throttle"
    symbol: str | None = None
    timestamp_utc: datetime | None = None
    timestamp: datetime | None = None  # alias
    message: str
    count: int | None = None
    window_seconds: int | float | None = None
    max_signals: int | None = None
    source_service: str | None = None
    pipeline_version: str | None = None
    verdict_before: str | None = None
    verdict_after: str | None = None

    @property
    def effective_timestamp(self) -> datetime:
        return self.timestamp_utc or self.timestamp or datetime.now(timezone.utc)


@router.post("/log")
async def receive_signal_throttle(
    payload: SignalThrottleWebhookPayload,
    x_wolf15_secret: str | None = Header(default=None),
):
    if not settings.webhook_auth_configured():
        raise HTTPException(status_code=503, detail="webhook authentication is not configured")
    if x_wolf15_secret is None or not secrets.compare_digest(
        x_wolf15_secret,
        settings.webhook_secret or "",
    ):
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    if payload.event != "signal_throttle":
        raise HTTPException(status_code=400, detail="unsupported event")

    ts = payload.effective_timestamp

    # Parse the message to extract symbol if not provided
    parsed = parse_signalthrottle(raw_message=payload.message, timestamp_utc=ts)
    symbol = payload.symbol or (parsed.symbol if parsed else None)

    if not symbol:
        raise HTTPException(status_code=400, detail="symbol not found in payload or message")

    repo = SignalRepository()
    event = LogEvent(
        symbol=symbol,
        event_type="SIGNAL_THROTTLE",
        timestamp_utc=ts,
        timestamp_wita=to_wita(ts),
        chart_time=to_chart_time(ts, settings.chart_time_offset_hours),
        raw_message=payload.message,
        source_service=payload.source_service or "wolf15-engine",
    )
    result = await repo.insert_signal_event(
        symbol=event.symbol,
        event_type=event.event_type,
        timestamp_utc=event.timestamp_utc,
        raw_message=event.raw_message,
        source_service=event.source_service,
        timestamp_wita=event.timestamp_wita,
        chart_time=event.chart_time,
        meta={**payload.model_dump(mode="json"), "source_path": "webhook"},
    )

    if result.get("duplicate"):
        return {
            "status": "duplicate_ignored",
            "symbol": symbol,
            "timestamp_utc": ts.isoformat(),
        }

    block = await repo.upsert_live_block_from_event(
        event,
        max_event_gap_seconds=settings.max_event_gap_seconds,
        chart_offset_hours=settings.chart_time_offset_hours,
    )

    logger.info("Webhook received: %s @ %s", symbol, ts.isoformat())

    return {
        "status": "accepted",
        "symbol": symbol,
        "timestamp_utc": ts.isoformat(),
        "event_id": result["id"],
        "block_id": block["id"],
        "block_action": block["action"],
        "pressure_status": block.get("pressure_status"),
        "pressure_grade": block.get("pressure_grade"),
    }
