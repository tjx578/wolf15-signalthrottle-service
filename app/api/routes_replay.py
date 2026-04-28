from __future__ import annotations

import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import require_dashboard_auth
from ..config import settings
from ..detector.sequence_builder import (
    build_canonical_sequences,
    make_block_hash,
    split_sequence_by_continuity_gap,
)
from ..models.log_event import LogEvent
from ..parser.signalthrottle_parser import parse_signalthrottle
from ..parser.timestamp_mapper import to_chart_time, to_wita
from ..planner.market_context import enrich_block_with_market_context
from ..scoring.pressure_grader import grade_pressure
from ..scoring.pressure_metrics import calculate_pressure_metrics
from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)
router = APIRouter()

# Matches typical Railway log timestamp prefix
_TS_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)"
)


class ReplayPayload(BaseModel):
    logs: str


@router.post("/logs")
async def replay_logs(
    payload: ReplayPayload,
    _: None = Depends(require_dashboard_auth),
):
    """Parse raw log text, detect blocks, compute grades, store results."""
    lines = payload.logs.strip().splitlines()
    events: list[LogEvent] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Extract timestamp
        ts_match = _TS_RE.search(line)
        if not ts_match:
            continue
        ts_str = ts_match.group("ts")
        if not ts_str.endswith("Z"):
            ts_str += "Z"
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        parsed = parse_signalthrottle(raw_message=line, timestamp_utc=ts)
        if not parsed:
            continue

        events.append(
            LogEvent(
                symbol=parsed.symbol,
                event_type="SIGNAL_THROTTLE",
                timestamp_utc=parsed.timestamp_utc,
                timestamp_wita=to_wita(parsed.timestamp_utc),
                chart_time=to_chart_time(
                    parsed.timestamp_utc, settings.chart_time_offset_hours
                ),
                raw_message=line,
            )
        )

    if not events:
        return {"status": "no_events_parsed", "line_count": len(lines)}

    # Store events
    repo = SignalRepository()
    stored = 0
    duplicates = 0
    for ev in events:
        result = await repo.insert_signal_event(
            symbol=ev.symbol,
            event_type=ev.event_type,
            timestamp_utc=ev.timestamp_utc,
            raw_message=ev.raw_message,
            timestamp_wita=ev.timestamp_wita,
            chart_time=ev.chart_time,
        )
        if result.get("duplicate"):
            duplicates += 1
        else:
            stored += 1

    # Detect canonical sequences over the GLOBAL chronological stream.
    # We deliberately do not group by symbol first: the canonical rule states
    # that a different pair appearing closes the previous block, even if the
    # original pair returns within max_gap_seconds.
    sequences = build_canonical_sequences(events, settings.max_event_gap_seconds)
    continuity_blocks = [
        block
        for sequence in sequences
        for block in split_sequence_by_continuity_gap(
            sequence,
            settings.max_continuity_gap_seconds,
        )
    ]
    block_results = []
    blocks_created = 0
    blocks_updated = 0
    trade_plan_count = 0

    for seq_events in continuity_blocks:
        symbol = seq_events[0].symbol
        metrics = calculate_pressure_metrics(seq_events)
        grade = grade_pressure(
            duration=metrics["duration_minutes"],
            event_count=metrics["event_count"],
            density=metrics["density_per_minute"],
            max_gap=metrics["max_gap_seconds"],
        )

        start = seq_events[0].timestamp_utc
        end = seq_events[-1].timestamp_utc
        block_hash = make_block_hash(seq_events)

        # Idempotent: same block_hash → updates the existing row, never
        # inserts a duplicate. Replaying the same logs N times yields the
        # same canonical block set.
        block_data = await repo.upsert_pressure_block_by_hash(
            block_hash=block_hash,
            symbol=symbol,
            start_utc=start,
            end_utc=end,
            start_wita=to_wita(start),
            end_wita=to_wita(end),
            chart_start_time=to_chart_time(
                start, settings.chart_time_offset_hours
            ),
            chart_end_time=to_chart_time(
                end, settings.chart_time_offset_hours
            ),
            duration_minutes=metrics["duration_minutes"],
            event_count=metrics["event_count"],
            density_per_minute=metrics["density_per_minute"],
            avg_gap_seconds=metrics["avg_gap_seconds"],
            max_gap_seconds=metrics["max_gap_seconds"],
            pressure_grade=grade,
            pressure_status="REPLAY",
            finalize_mode="REPLAY_FINALIZE",
        )
        if block_data["action"] == "created":
            blocks_created += 1
        else:
            blocks_updated += 1

        block = {
            "id": block_data["id"],
            "symbol": symbol,
            "start_utc": start,
            "end_utc": end,
            "start_wita": to_wita(start),
            "end_wita": to_wita(end),
            "chart_start_time": to_chart_time(
                start, settings.chart_time_offset_hours
            ),
            "chart_end_time": to_chart_time(
                end, settings.chart_time_offset_hours
            ),
            "duration_minutes": metrics["duration_minutes"],
            "event_count": metrics["event_count"],
            "density_per_minute": metrics["density_per_minute"],
            "avg_gap_seconds": metrics["avg_gap_seconds"],
            "max_gap_seconds": metrics["max_gap_seconds"],
            "pressure_grade": grade,
            "pressure_status": "REPLAY",
            "block_relation": None,
            "finalize_mode": "REPLAY_FINALIZE",
        }

        trade_plan = await enrich_block_with_market_context(block, repo)
        if trade_plan:
            trade_plan_count += 1

        block_results.append(
            {
                "symbol": symbol,
                "block_id": block_data["id"],
                "block_hash": block_hash,
                "action": block_data["action"],
                "event_count": metrics["event_count"],
                "duration_minutes": metrics["duration_minutes"],
                "density_per_minute": metrics["density_per_minute"],
                "pressure_grade": grade,
                "trade_plan_created": trade_plan is not None,
            }
        )

    return {
        "status": "processed",
        "events_parsed": len(events),
        "events_stored": stored,
        "duplicates_skipped": duplicates,
        "canonical_blocks_detected": len(block_results),
        "blocks_created": blocks_created,
        "blocks_updated": blocks_updated,
        "trade_plans_created": trade_plan_count,
        "blocks": block_results,
    }
