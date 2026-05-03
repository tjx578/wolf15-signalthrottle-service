from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import require_dashboard_auth
from ..config import settings
from ..detector.sequence_builder import (
    build_canonical_sequences,
    make_block_hash,
)
from ..ingestion.engine_log_sync import parse_engine_log_entries
from ..models.log_event import LogEvent
from ..parser.signalthrottle_parser import parse_signalthrottle
from ..parser.timestamp_mapper import to_chart_time, to_wita
from ..planner.market_context import enrich_block_with_market_context
from ..scoring.pressure_grader import grade_pressure
from ..scoring.pressure_metrics import calculate_pressure_metrics
from ..scoring.phase1_classification import pressure_temperature, theme_cluster
from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)
router = APIRouter()

class ReplayPayload(BaseModel):
    logs: str


@router.post("/logs")
async def replay_logs(
    payload: ReplayPayload,
    _: None = Depends(require_dashboard_auth),
):
    """Parse raw log text, detect blocks, compute grades, store results.
    
    Replay is idempotent: same block_hash never creates duplicate blocks.
    Relaying same logs N times yields identical results.
    """
    if not payload.logs or not payload.logs.strip():
        return {
            "status": "error",
            "error": "empty_input",
            "message": "Logs field is empty. Please paste raw SignalThrottle logs.",
        }
    
    try:
        entries = parse_engine_log_entries(payload.logs, source_path="replay")
        events: list[LogEvent] = []

        for entry in entries:
            if entry.timestamp_utc is None:
                continue
            parsed = parse_signalthrottle(
                raw_message=entry.message,
                timestamp_utc=entry.timestamp_utc,
            )
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
                    raw_message=entry.message,
                    source_service=entry.source_service,
                )
            )

        if not events:
            return {
                "status": "no_events_parsed",
                "line_count": len(entries),
                "message": f"No valid SignalThrottle logs found in {len(entries)} rows. Check timestamp format (expected: YYYY-MM-DDTHH:MM:SSZ)"
            }

        # Store events
        repo = SignalRepository()
        stored = 0
        duplicates = 0
        for ev in events:
            try:
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
            except Exception as e:
                logger.warning(f"Failed to insert signal event: {e}")
                continue

        # Detect canonical sequences over the GLOBAL chronological stream.
        # We deliberately do not group by symbol first: the canonical rule states
        # that a different pair appearing closes the previous block, even if the
        # original pair returns within max_gap_seconds.
        try:
            sequences = build_canonical_sequences(events, max_gap_seconds=None)
        except Exception as e:
            logger.exception("Failed to build canonical sequences")
            return {
                "status": "error",
                "error": "sequence_detection_failed",
                "message": str(e)[:200],
                "events_parsed": len(events),
                "events_stored": stored,
            }

        continuity_blocks = sequences
        block_results = []
        blocks_created = 0
        blocks_updated = 0
        trade_plan_count = 0
        wave_counts: dict[str, int] = {}

        for index, seq_events in enumerate(continuity_blocks):
            try:
                symbol = seq_events[0].symbol
                wave_counts[symbol] = wave_counts.get(symbol, 0) + 1
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
                interrupted_by = (
                    continuity_blocks[index + 1][0].symbol
                    if index + 1 < len(continuity_blocks) and continuity_blocks[index + 1]
                    else None
                )

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
                    block_mode="SAME_PAIR_SEQUENCE",
                    pressure_temperature=pressure_temperature(metrics["density_per_minute"]),
                    wave_count=wave_counts[symbol],
                    interrupted_by=interrupted_by,
                    theme_cluster=theme_cluster(symbol),
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
                    "block_mode": "SAME_PAIR_SEQUENCE",
                    "pressure_temperature": pressure_temperature(metrics["density_per_minute"]),
                    "wave_count": wave_counts[symbol],
                    "interrupted_by": interrupted_by,
                    "theme_cluster": theme_cluster(symbol),
                }

                trade_plan = (
                    await enrich_block_with_market_context(block, repo)
                    if settings.enable_trade_plans
                    else None
                )
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
                        "max_gap_seconds": metrics["max_gap_seconds"],
                        "pressure_grade": grade,
                        "block_mode": "SAME_PAIR_SEQUENCE",
                        "pressure_temperature": pressure_temperature(metrics["density_per_minute"]),
                        "wave_count": wave_counts[symbol],
                        "interrupted_by": interrupted_by,
                        "theme_cluster": theme_cluster(symbol),
                        "trade_plan_created": trade_plan is not None,
                    }
                )
            except Exception as e:
                logger.exception(f"Failed to process block for symbol: {e}")
                # Continue processing other blocks rather than crashing
                continue

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

    except Exception as e:
        logger.exception("Unexpected error in replay_logs")
        return {
            "status": "error",
            "error": "internal_error",
            "message": str(e)[:200],
        }
