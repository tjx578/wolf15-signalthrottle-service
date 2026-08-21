from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..config import settings
from ..detector.sequence_builder import build_canonical_sequences
from ..models.log_event import LogEvent
from ..parser.signalthrottle_parser import parse_signalthrottle
from ..parser.timestamp_mapper import to_chart_time, to_wita
from ..scoring.pressure_grader import grade_pressure
from ..scoring.pressure_metrics import calculate_pressure_metrics
from ..scoring.phase1_classification import (
    phase1_signal_status,
    pressure_temperature as classify_pressure_temperature,
    theme_cluster as classify_theme_cluster,
)
from .postgres import get_cursor
from ..utils.json_utils import make_engine_log_hash, make_event_hash

logger = logging.getLogger(__name__)


class SignalRepository:
    """Central repository for all DB operations."""

    # ----- signal_events -----

    async def insert_signal_event(
        self,
        *,
        symbol: str,
        event_type: str,
        timestamp_utc: datetime,
        raw_message: str,
        source_service: str = "wolf15-engine",
        timestamp_wita: str | None = None,
        chart_time: str | None = None,
        meta: dict | None = None,
    ) -> dict:
        event_hash = make_event_hash(symbol, timestamp_utc, raw_message)

        async with get_cursor() as cur:
            # Check duplicate
            await cur.execute(
                """
                SELECT id FROM signal_events
                WHERE event_hash = %s
                   OR (
                        symbol = %s
                    AND timestamp_utc = %s
                    AND source_service = %s
                    AND event_type = %s
                   )
                ORDER BY id ASC
                LIMIT 1
                """,
                (event_hash, symbol, timestamp_utc, source_service, event_type),
            )
            existing = await cur.fetchone()
            if existing:
                return {"id": existing["id"], "duplicate": True}

            await cur.execute(
                """
                INSERT INTO signal_events
                    (symbol, event_type, timestamp_utc, timestamp_wita, chart_time,
                     raw_message, source_service, event_hash, meta)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    symbol,
                    event_type,
                    timestamp_utc,
                    timestamp_wita,
                    chart_time,
                    raw_message,
                    source_service,
                    event_hash,
                    _json_or_none(meta),
                ),
            )
            row = await cur.fetchone()
            assert row is not None
            return {"id": row["id"], "duplicate": False}

    # ----- raw engine logs -----

    async def insert_engine_log_entry(
        self,
        *,
        timestamp_utc: datetime | None,
        message: str,
        severity: str | None = None,
        attributes: Any = None,
        tags: Any = None,
        source_service: str = "wolf15-engine",
        source_path: str = "engine_log_sync",
        is_signalthrottle: bool = False,
        parse_status: str | None = None,
        symbol: str | None = None,
        signal_count: int | None = None,
        window_seconds: int | None = None,
        max_signals: int | None = None,
        raw_payload: Any = None,
    ) -> dict:
        log_hash = make_engine_log_hash(timestamp_utc, message, source_service)

        async with get_cursor() as cur:
            await cur.execute(
                "SELECT id FROM engine_log_entries WHERE log_hash = %s",
                (log_hash,),
            )
            existing = await cur.fetchone()
            if existing:
                return {"id": existing["id"], "duplicate": True}

            await cur.execute(
                """
                INSERT INTO engine_log_entries
                    (timestamp_utc, message, severity, attributes, tags,
                     source_service, source_path, log_hash, is_signalthrottle,
                     parse_status, symbol, signal_count, window_seconds,
                     max_signals, raw_payload)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    timestamp_utc,
                    message,
                    severity,
                    _json_or_none(attributes),
                    _json_or_none(tags),
                    source_service,
                    source_path,
                    log_hash,
                    is_signalthrottle,
                    parse_status,
                    symbol,
                    signal_count,
                    window_seconds,
                    max_signals,
                    _json_or_none(raw_payload),
                ),
            )
            row = await cur.fetchone()
            assert row is not None
            return {"id": row["id"], "duplicate": False}

    # ----- pressure_blocks -----

    async def upsert_active_block(
        self,
        *,
        symbol: str,
        start_utc: datetime,
        end_utc: datetime,
        start_wita: str | None = None,
        end_wita: str | None = None,
        chart_start_time: str | None = None,
        chart_end_time: str | None = None,
        duration_minutes: float,
        event_count: int,
        density_per_minute: float,
        avg_gap_seconds: float | None = None,
        max_gap_seconds: float | None = None,
        pressure_grade: str,
        pressure_status: str | None = None,
        block_relation: str | None = None,
        previous_block_id: int | None = None,
        finalize_mode: str | None = None,
        last_event_utc: datetime | None = None,
        block_mode: str = "SAME_PAIR_SEQUENCE",
        pressure_temperature: str | None = None,
        wave_count: int = 1,
        interrupted_by: str | None = None,
        theme_cluster: str | None = None,
    ) -> dict:
        effective_last_event_utc = last_event_utc or end_utc
        effective_temperature = pressure_temperature or classify_pressure_temperature(
            density_per_minute
        )
        effective_theme = theme_cluster or classify_theme_cluster(symbol)
        async with get_cursor() as cur:
            # Find existing active block for this symbol
            await cur.execute(
                """
                SELECT id FROM pressure_blocks
                WHERE symbol = %s AND is_active = TRUE
                ORDER BY end_utc DESC LIMIT 1
                """,
                (symbol,),
            )
            existing = await cur.fetchone()

            if existing:
                await cur.execute(
                    """
                    UPDATE pressure_blocks SET
                        end_utc = %s, end_wita = %s, chart_end_time = %s,
                        last_event_utc = %s,
                        duration_minutes = %s, event_count = %s,
                        density_per_minute = %s, avg_gap_seconds = %s,
                        max_gap_seconds = %s, pressure_grade = %s,
                        pressure_status = %s, block_relation = %s,
                        finalize_mode = %s,
                        block_mode = %s,
                        pressure_temperature = %s,
                        wave_count = %s,
                        interrupted_by = %s,
                        theme_cluster = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (
                        end_utc, end_wita, chart_end_time,
                        effective_last_event_utc,
                        duration_minutes, event_count,
                        density_per_minute, avg_gap_seconds,
                        max_gap_seconds, pressure_grade,
                        pressure_status, block_relation,
                        finalize_mode,
                        block_mode,
                        effective_temperature,
                        wave_count,
                        interrupted_by,
                        effective_theme,
                        existing["id"],
                    ),
                )
                row = await cur.fetchone()
                assert row is not None
                result = {
                    "id": row["id"],
                    "action": "updated",
                    "pressure_status": pressure_status,
                    "pressure_grade": pressure_grade,
                }
                await self.refresh_pressure_series(symbol=symbol)
                return result
            else:
                await cur.execute(
                    """
                    INSERT INTO pressure_blocks
                        (symbol, start_utc, end_utc, start_wita, end_wita,
                         chart_start_time, chart_end_time, last_event_utc,
                         duration_minutes, event_count, density_per_minute,
                         avg_gap_seconds, max_gap_seconds,
                         pressure_grade, pressure_status, block_relation,
                         previous_block_id, finalize_mode, block_mode,
                         pressure_temperature, wave_count, interrupted_by,
                         theme_cluster, is_active)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
                    RETURNING id
                    """,
                    (
                        symbol, start_utc, end_utc, start_wita, end_wita,
                        chart_start_time, chart_end_time,
                        effective_last_event_utc,
                        duration_minutes, event_count, density_per_minute,
                        avg_gap_seconds, max_gap_seconds,
                        pressure_grade, pressure_status, block_relation,
                        previous_block_id, finalize_mode, block_mode,
                        effective_temperature, wave_count, interrupted_by,
                        effective_theme,
                    ),
                )
                row = await cur.fetchone()
                assert row is not None
                result = {
                    "id": row["id"],
                    "action": "created",
                    "pressure_status": pressure_status,
                    "pressure_grade": pressure_grade,
                }
                await self.refresh_pressure_series(symbol=symbol)
                return result

    async def get_active_block(self, symbol: str) -> dict | None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM pressure_blocks
                WHERE symbol = %s AND is_active = TRUE
                ORDER BY end_utc DESC LIMIT 1
                """,
                (symbol,),
            )
            return await cur.fetchone()

    async def get_signal_events_in_range(
        self,
        symbol: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[LogEvent]:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT symbol, event_type, timestamp_utc, timestamp_wita,
                       chart_time, raw_message, source_service
                FROM signal_events
                WHERE symbol = %s
                  AND timestamp_utc >= %s
                  AND timestamp_utc <= %s
                ORDER BY timestamp_utc ASC
                """,
                (symbol, start_utc, end_utc),
            )
            rows = await cur.fetchall()

        return [
            LogEvent(
                symbol=row["symbol"],
                event_type=row["event_type"],
                timestamp_utc=row["timestamp_utc"],
                timestamp_wita=row.get("timestamp_wita"),
                chart_time=row.get("chart_time"),
                raw_message=row["raw_message"],
                source_service=row.get("source_service") or "wolf15-engine",
            )
            for row in rows
        ]

    async def mark_other_active_blocks_cooling(self, symbol: str) -> None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                UPDATE pressure_blocks
                SET pressure_status = 'COOLING', updated_at = NOW()
                WHERE is_active = TRUE
                  AND symbol <> %s
                  AND pressure_status = 'ACTIVE'
                """,
                (symbol,),
            )

    async def finalize_other_active_blocks_on_pair_replacement(
        self, symbol: str
    ) -> list[dict]:
        """When a different pair becomes active, soft-finalize every other
        active block immediately. The previous block is *closed*, not merely
        cooling, because the canonical rule states "pair replacement closes
        the block."

        Returns the list of finalized blocks (id + symbol) so callers can run
        downstream enrichment or auditing.
        """
        async with get_cursor() as cur:
            await cur.execute(
                """
                UPDATE pressure_blocks
                SET is_active = FALSE,
                    pressure_status = 'SOFT_FINALIZED',
                    finalize_mode = 'PAIR_REPLACEMENT',
                    interrupted_by = %s,
                    updated_at = NOW()
                WHERE is_active = TRUE
                  AND symbol <> %s
                RETURNING id, symbol
                """,
                (symbol, symbol),
            )
            rows = await cur.fetchall()
        for row in rows:
            await self.refresh_pressure_series(symbol=row["symbol"])
        return rows

    async def upsert_pressure_block_by_hash(
        self,
        *,
        block_hash: str,
        symbol: str,
        start_utc: datetime,
        end_utc: datetime,
        start_wita: str | None = None,
        end_wita: str | None = None,
        chart_start_time: str | None = None,
        chart_end_time: str | None = None,
        duration_minutes: float,
        event_count: int,
        density_per_minute: float,
        avg_gap_seconds: float | None = None,
        max_gap_seconds: float | None = None,
        pressure_grade: str,
        pressure_status: str | None = None,
        block_relation: str | None = None,
        previous_block_id: int | None = None,
        finalize_mode: str | None = None,
        block_mode: str = "SAME_PAIR_SEQUENCE",
        pressure_temperature: str | None = None,
        wave_count: int = 1,
        interrupted_by: str | None = None,
        theme_cluster: str | None = None,
    ) -> dict:
        """Idempotent block upsert keyed on canonical block_hash.

        Re-replaying the same logs produces the same hash and therefore
        updates the existing row instead of inserting a duplicate. is_active
        is forced to FALSE because hash-based writes only happen for
        finalized canonical sequences (replay path).
        """
        effective_temperature = pressure_temperature or classify_pressure_temperature(
            density_per_minute
        )
        effective_theme = theme_cluster or classify_theme_cluster(symbol)
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT id FROM pressure_blocks WHERE block_hash = %s
                """,
                (block_hash,),
            )
            existing = await cur.fetchone()

            if existing:
                await cur.execute(
                    """
                    UPDATE pressure_blocks SET
                        symbol = %s,
                        start_utc = %s, end_utc = %s,
                        start_wita = %s, end_wita = %s,
                        chart_start_time = %s, chart_end_time = %s,
                        last_event_utc = %s,
                        duration_minutes = %s, event_count = %s,
                        density_per_minute = %s, avg_gap_seconds = %s,
                        max_gap_seconds = %s, pressure_grade = %s,
                        pressure_status = %s, block_relation = %s,
                        previous_block_id = %s, finalize_mode = %s,
                        block_mode = %s, pressure_temperature = %s,
                        wave_count = %s, interrupted_by = %s,
                        theme_cluster = %s,
                        is_active = FALSE,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (
                        symbol, start_utc, end_utc,
                        start_wita, end_wita,
                        chart_start_time, chart_end_time,
                        end_utc,
                        duration_minutes, event_count,
                        density_per_minute, avg_gap_seconds,
                        max_gap_seconds, pressure_grade,
                        pressure_status, block_relation,
                        previous_block_id, finalize_mode,
                        block_mode, effective_temperature,
                        wave_count, interrupted_by,
                        effective_theme,
                        existing["id"],
                    ),
                )
                row = await cur.fetchone()
                assert row is not None
                action = "updated"
            else:
                await cur.execute(
                    """
                    INSERT INTO pressure_blocks
                        (symbol, start_utc, end_utc, start_wita, end_wita,
                         chart_start_time, chart_end_time, last_event_utc,
                         duration_minutes, event_count, density_per_minute,
                         avg_gap_seconds, max_gap_seconds,
                         pressure_grade, pressure_status, block_relation,
                         previous_block_id, finalize_mode, block_hash,
                         block_mode, pressure_temperature, wave_count,
                         interrupted_by, theme_cluster, is_active)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE)
                    RETURNING id
                    """,
                    (
                        symbol, start_utc, end_utc, start_wita, end_wita,
                        chart_start_time, chart_end_time,
                        end_utc,
                        duration_minutes, event_count, density_per_minute,
                        avg_gap_seconds, max_gap_seconds,
                        pressure_grade, pressure_status, block_relation,
                        previous_block_id, finalize_mode, block_hash,
                        block_mode, effective_temperature, wave_count,
                        interrupted_by, effective_theme,
                    ),
                )
                row = await cur.fetchone()
                assert row is not None
                action = "created"

        await self.refresh_pressure_series(symbol=symbol)
        return {
            "id": row["id"],
            "action": action,
            "pressure_status": pressure_status,
            "pressure_grade": pressure_grade,
            "block_hash": block_hash,
        }

    async def upsert_live_block_from_event(
        self,
        event: LogEvent,
        *,
        max_event_gap_seconds: int,
        chart_offset_hours: int,
    ) -> dict:
        # Canonical rule: a different pair becoming active CLOSES every other
        # active block. We finalize them with PAIR_REPLACEMENT so they cannot
        # be silently re-extended by a late event of the previous pair.
        await self.finalize_other_active_blocks_on_pair_replacement(event.symbol)

        existing = await self.get_active_block(event.symbol)
        previous_block_id: int | None = None
        start_utc = event.timestamp_utc

        if existing:
            previous_block_id = existing.get("previous_block_id")
            # Phase 1 rule: a large same-pair gap does not split the block.
            # Gap size remains visible through max_gap/density temperature.
            start_utc = existing["start_utc"]

        if existing is None:
            last_finalized = await self.get_last_finalized_block(event.symbol)
            previous_block_id = last_finalized["id"] if last_finalized else previous_block_id

        events = await self.get_signal_events_in_range(
            event.symbol,
            start_utc,
            event.timestamp_utc,
        )
        metrics = calculate_pressure_metrics(events)
        pressure_grade = grade_pressure(
            duration=metrics["duration_minutes"],
            event_count=metrics["event_count"],
            density=metrics["density_per_minute"],
            max_gap=metrics["max_gap_seconds"],
        )

        return await self.upsert_active_block(
            symbol=event.symbol,
            start_utc=start_utc,
            end_utc=event.timestamp_utc,
            start_wita=to_wita(start_utc),
            end_wita=to_wita(event.timestamp_utc),
            chart_start_time=to_chart_time(start_utc, chart_offset_hours),
            chart_end_time=to_chart_time(event.timestamp_utc, chart_offset_hours),
            duration_minutes=metrics["duration_minutes"],
            event_count=metrics["event_count"],
            density_per_minute=metrics["density_per_minute"],
            avg_gap_seconds=metrics["avg_gap_seconds"],
            max_gap_seconds=metrics["max_gap_seconds"],
            pressure_grade=pressure_grade,
            pressure_status="ACTIVE",
            block_relation=None,
            previous_block_id=previous_block_id,
            finalize_mode=None,
            last_event_utc=event.timestamp_utc,
        )

    async def mark_block_continuity_split(self, block_id: int) -> None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                UPDATE pressure_blocks
                SET is_active = FALSE,
                    pressure_status = 'SOFT_FINALIZED',
                    finalize_mode = 'CONTINUITY_SPLIT',
                    updated_at = NOW()
                WHERE id = %s
                RETURNING symbol
                """,
                (block_id,),
            )
            row = await cur.fetchone()
        if row:
            await self.refresh_pressure_series(symbol=row["symbol"])

    async def finalize_block(self, block_id: int, finalize_mode: str) -> None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                UPDATE pressure_blocks
                SET is_active = FALSE, finalize_mode = %s
                WHERE id = %s
                """,
                (finalize_mode, block_id),
            )

    async def mark_block_market_context_status(
        self,
        block_id: int,
        *,
        market_context_status: str,
        trade_plan_status: str,
        pending_reason: str | None = None,
    ) -> None:
        """Persist enrichment outcome on the block itself.

        Status values used:
          - market_context_status:
              REQUESTED, READY, OHLC_FETCH_FAILED, FINNHUB_KEY_MISSING,
              DISABLED, PHASE_UNCLASSIFIED
          - trade_plan_status:
              NOT_REQUIRED, REQUIRED, PENDING_MARKET_CONTEXT, READY,
              NO_TRADE_CONTEXT
        """
        async with get_cursor() as cur:
            await cur.execute(
                """
                UPDATE pressure_blocks
                SET market_context_status = %s,
                    trade_plan_status = %s,
                    pending_reason = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    market_context_status,
                    trade_plan_status,
                    pending_reason,
                    block_id,
                ),
            )

    async def get_active_or_cooling_blocks(self) -> list[dict]:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM pressure_blocks
                WHERE is_active = TRUE
                  AND pressure_status IN ('ACTIVE', 'COOLING')
                ORDER BY end_utc DESC
                """
            )
            return await cur.fetchall()

    async def mark_block_cooling(self, block_id: int) -> None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                UPDATE pressure_blocks
                SET pressure_status = 'COOLING', updated_at = NOW()
                WHERE id = %s AND is_active = TRUE
                RETURNING symbol
                """,
                (block_id,),
            )
            row = await cur.fetchone()
        if row:
            await self.refresh_pressure_series(symbol=row["symbol"])

    async def mark_block_soft_finalized(self, block_id: int) -> None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                UPDATE pressure_blocks
                SET is_active = FALSE,
                    pressure_status = 'SOFT_FINALIZED',
                    finalize_mode = 'SOFT_FINALIZED',
                    updated_at = NOW()
                WHERE id = %s
                RETURNING symbol
                """,
                (block_id,),
            )
            row = await cur.fetchone()
        if row:
            await self.refresh_pressure_series(symbol=row["symbol"])

    async def mark_block_hard_finalized(self, block_id: int) -> None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                UPDATE pressure_blocks
                SET is_active = FALSE,
                    pressure_status = 'HARD_FINALIZED',
                    finalize_mode = 'HARD_FINALIZED',
                    updated_at = NOW()
                WHERE id = %s
                RETURNING symbol
                """,
                (block_id,),
            )
            row = await cur.fetchone()
        if row:
            await self.refresh_pressure_series(symbol=row["symbol"])

    async def get_active_blocks(self) -> list[dict]:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM pressure_blocks
                WHERE is_active = TRUE
                ORDER BY end_utc DESC
                """
            )
            return await cur.fetchall()

    async def get_block_history(
        self, symbol: str | None = None, limit: int | None = 50
    ) -> list[dict]:
        async with get_cursor() as cur:
            if symbol and limit is not None:
                await cur.execute(
                    """
                    SELECT * FROM pressure_blocks
                    WHERE symbol = %s
                    ORDER BY end_utc DESC LIMIT %s
                    """,
                    (symbol, limit),
                )
            elif symbol:
                await cur.execute(
                    """
                    SELECT * FROM pressure_blocks
                    WHERE symbol = %s
                    ORDER BY end_utc DESC
                    """,
                    (symbol,),
                )
            elif limit is not None:
                await cur.execute(
                    """
                    SELECT * FROM pressure_blocks
                    ORDER BY end_utc DESC LIMIT %s
                    """,
                    (limit,),
                )
            else:
                await cur.execute(
                    """
                    SELECT * FROM pressure_blocks
                    ORDER BY end_utc DESC
                    """
                )
            return await cur.fetchall()

    async def get_signal_history(
        self,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        return await self.get_block_history(symbol=symbol, limit=limit)

    async def get_latest_pressure_observations(
        self,
        limit: int = 50,
        bucket: str = "all",
    ) -> list[dict]:
        """Return an observational-only projection of pressure blocks.

        This projection deliberately does not join market snapshots, trade
        plans, outcomes, or execution-oriented tables.  Legacy rows remain in
        storage for preservation, but the production observer does not expose
        them as live authority.
        """
        normalized_bucket = bucket.strip().lower()
        if normalized_bucket not in {"all", "failed", "radar", "priority", "active"}:
            normalized_bucket = "all"

        rows = await self.get_block_history(limit=max(limit * 20, 100))
        observations: list[dict] = []
        eligible_grades = {"B+", "A-", "A", "A+"}

        for row in rows:
            grade = str(row.get("pressure_grade") or "UNKNOWN")
            is_active = bool(row.get("is_active"))
            if grade == "FAILED_MIN_DURATION":
                observation_bucket = "failed"
                reason_code = "FAILED_MIN_DURATION"
            elif grade == "REJECT":
                observation_bucket = "radar"
                reason_code = "OBSERVED_GAP_EXCEEDS_POLICY"
            elif grade in eligible_grades:
                observation_bucket = "priority"
                reason_code = "OWNER_PRIORITY_PRESSURE"
            else:
                observation_bucket = "radar"
                reason_code = "PRESSURE_BELOW_OWNER_PRIORITY"

            if normalized_bucket == "active" and not is_active:
                continue
            if normalized_bucket not in {"all", "active", observation_bucket}:
                continue

            symbol = str(row.get("symbol") or "-")
            observations.append(
                {
                    "id": row.get("id"),
                    "block_id": row.get("id"),
                    "symbol": symbol,
                    "start_utc": row.get("start_utc"),
                    "end_utc": row.get("end_utc"),
                    "start_wita": row.get("start_wita"),
                    "end_wita": row.get("end_wita"),
                    "duration_minutes": row.get("duration_minutes"),
                    "event_count": row.get("event_count"),
                    "density_per_minute": row.get("density_per_minute"),
                    "avg_gap_seconds": row.get("avg_gap_seconds"),
                    "max_gap_seconds": row.get("max_gap_seconds"),
                    "pressure_grade": grade,
                    "pressure_status": row.get("pressure_status"),
                    "finalize_mode": row.get("finalize_mode"),
                    "block_mode": row.get("block_mode"),
                    "pressure_temperature": row.get("pressure_temperature"),
                    "wave_count": row.get("wave_count"),
                    "interrupted_by": row.get("interrupted_by"),
                    "theme_cluster": row.get("theme_cluster"),
                    "is_active": is_active,
                    "observation_bucket": observation_bucket,
                    "reason_code": reason_code,
                    "display_message": f"{symbol} {grade} pressure observation.",
                    "source_authority": "LEGACY_DERIVED_LOG",
                    "raw_coverage": "RAW_COVERAGE_UNKNOWN",
                    "expected_pair_admission": "NOT_EVALUATED",
                    "consumer_authority": "OBSERVATIONAL_ONLY",
                    "valid_for_execution": False,
                    "execution_command_allowed": False,
                }
            )
            if len(observations) >= limit:
                break

        return observations

    async def refresh_pressure_series(self, symbol: str | None = None) -> None:
        rows = await self.get_block_history(symbol=symbol, limit=None)
        merged = _merge_pressure_series(
            rows,
            merge_gap_seconds=settings.max_event_gap_seconds,
        )

        async with get_cursor() as cur:
            if symbol:
                await cur.execute(
                    "DELETE FROM pressure_series WHERE symbol = %s",
                    (symbol,),
                )
            else:
                await cur.execute("DELETE FROM pressure_series")

            for series in merged:
                await cur.execute(
                    """
                    INSERT INTO pressure_series (
                        symbol,
                        start_utc,
                        end_utc,
                        duration_minutes,
                        event_count,
                        density_per_minute,
                        max_gap_seconds,
                        block_count,
                        block_ids,
                        latest_block_id,
                        latest_trade_plan_id,
                        latest_pressure_grade,
                        best_pressure_grade,
                        best_valid_block_grade,
                        series_reason,
                        pressure_status,
                        finalize_mode,
                        is_active,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
                        (
                            SELECT id
                            FROM trade_plans
                            WHERE block_id = %s
                            ORDER BY created_at DESC
                            LIMIT 1
                        ),
                        %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                    """,
                    (
                        series["symbol"],
                        series["start_utc"],
                        series["end_utc"],
                        series["duration_minutes"],
                        series["event_count"],
                        series["density_per_minute"],
                        series["max_gap_seconds"],
                        series["block_count"],
                        _json_or_none(series["block_ids"]),
                        series["latest_block_id"],
                        series["latest_block_id"],
                        series["latest_pressure_grade"],
                        series["best_pressure_grade"],
                        series["best_valid_block_grade"],
                        series["series_reason"],
                        series["pressure_status"],
                        series["finalize_mode"],
                        series["is_active"],
                    ),
                )

    async def get_signal_series(
        self,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        async with get_cursor() as cur:
            if symbol:
                await cur.execute(
                    """
                    SELECT * FROM pressure_series
                    WHERE symbol = %s
                    ORDER BY end_utc DESC, id DESC
                    LIMIT %s
                    """,
                    (symbol, limit),
                )
            else:
                await cur.execute(
                    """
                    SELECT * FROM pressure_series
                    ORDER BY end_utc DESC, id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            rows = await cur.fetchall()
            return [_with_series_metadata(row) for row in rows]

    async def get_signal_series_detail(self, symbol: str) -> dict | None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM pressure_series
                WHERE symbol = %s
                ORDER BY end_utc DESC, id DESC
                LIMIT 1
                """,
                (symbol,),
            )
            series = await cur.fetchone()

        if not series:
            return None

        series_events = await self.get_signal_events_in_range(
            symbol,
            series["start_utc"],
            series["end_utc"],
        )
        throttle_states = _build_signal_throttle_states(series_events)

        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT pb.*
                FROM pressure_blocks pb
                WHERE pb.symbol = %s
                  AND pb.start_utc <= %s
                  AND pb.end_utc >= %s
                ORDER BY pb.end_utc DESC, pb.id DESC
                """,
                (symbol, series["end_utc"], series["start_utc"]),
            )
            blocks = await cur.fetchall()
        series_block_ids = _series_block_ids(series)
        if series_block_ids:
            blocks = [row for row in blocks if _row_block_id(row) in series_block_ids]
        blocks = [
            _with_density_metadata(row)
            for row in sorted(
                _collapse_replay_overlap_block_rows(_dedupe_exact_pressure_block_rows(blocks)),
                key=lambda row: (row.get("end_utc"), row.get("id") or 0),
                reverse=True,
            )
        ]

        return {
            "series": _with_series_metadata(series),
            "blocks": blocks,
            "throttle_states": throttle_states,
            "raw_signal_events": len(series_events),
            "consumer_authority": "OBSERVATIONAL_ONLY",
            "valid_for_execution": False,
        }

    async def get_last_finalized_block(self, symbol: str) -> dict | None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM pressure_blocks
                WHERE symbol = %s AND is_active = FALSE
                ORDER BY end_utc DESC LIMIT 1
                """,
                (symbol,),
            )
            return await cur.fetchone()

    async def get_previous_block_before(
        self,
        symbol: str,
        start_utc: Any,
        *,
        exclude_block_id: int | None = None,
    ) -> dict | None:
        async with get_cursor() as cur:
            if exclude_block_id is None:
                await cur.execute(
                    """
                    SELECT * FROM pressure_blocks
                    WHERE symbol = %s
                      AND end_utc <= %s
                    ORDER BY end_utc DESC, id DESC
                    LIMIT 1
                    """,
                    (symbol, start_utc),
                )
            else:
                await cur.execute(
                    """
                    SELECT * FROM pressure_blocks
                    WHERE symbol = %s
                      AND end_utc <= %s
                      AND id <> %s
                    ORDER BY end_utc DESC, id DESC
                    LIMIT 1
                    """,
                    (symbol, start_utc, exclude_block_id),
                )
            return await cur.fetchone()

    # ----- trade_plans -----

    async def insert_trade_plan(self, block_id: int, plan: dict) -> int:
        async with get_cursor() as cur:
            await cur.execute(
                """
                INSERT INTO trade_plans
                    (block_id, symbol, pressure_status, signal_bucket,
                     pressure_grade, execution_grade,
                     execution_side, chart_phase, reason_code, action, entry_zone, breakout_level,
                     reclaim_level, invalidation, tp1, tp2, tp3,
                     message, payload)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                RETURNING id
                """,
                (
                    block_id,
                    plan["symbol"],
                    plan.get("pressure_status"),
                    plan.get("signal_bucket"),
                    plan["pressure_grade"],
                    plan["execution_grade"],
                    plan.get("execution_side"),
                    plan.get("chart_phase"),
                    plan.get("reason_code"),
                    plan["action"],
                    plan.get("entry_zone"),
                    plan.get("breakout_level"),
                    plan.get("reclaim_level"),
                    plan.get("invalidation"),
                    plan.get("tp1"),
                    plan.get("tp2"),
                    plan.get("tp3"),
                    plan.get("message"),
                    _json_or_none(plan.get("payload") or {}),
                ),
            )
            row = await cur.fetchone()
            assert row is not None
            return row["id"]

    async def get_latest_trade_plans(
        self,
        limit: int = 20,
        bucket: str = "all",
    ) -> list[dict]:
        async with get_cursor() as cur:
            if bucket == "actionable":
                await cur.execute(
                    """
                    SELECT tp.*, pb.start_wita AS signal_start_wita,
                           pb.end_wita AS signal_end_wita,
                           pb.duration_minutes, pb.event_count,
                           pb.density_per_minute,
                           ms.h4_structure,
                           ms.h4_context_type
                    FROM trade_plans tp
                    LEFT JOIN pressure_blocks pb ON tp.block_id = pb.id
                    LEFT JOIN LATERAL (
                        SELECT h4_structure, h4_context_type
                        FROM market_snapshots ms
                        WHERE ms.block_id = pb.id
                        ORDER BY ms.created_at DESC
                        LIMIT 1
                    ) ms ON TRUE
                    WHERE tp.execution_grade IN ('A+', 'A')
                      AND tp.action <> 'NO_TRADE_WAIT_CONTEXT'
                    ORDER BY tp.created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            elif bucket == "watchlist":
                await cur.execute(
                    """
                    SELECT tp.*, pb.start_wita AS signal_start_wita,
                           pb.end_wita AS signal_end_wita,
                           pb.duration_minutes, pb.event_count,
                           pb.density_per_minute,
                           ms.h4_structure,
                           ms.h4_context_type
                    FROM trade_plans tp
                    LEFT JOIN pressure_blocks pb ON tp.block_id = pb.id
                    LEFT JOIN LATERAL (
                        SELECT h4_structure, h4_context_type
                        FROM market_snapshots ms
                        WHERE ms.block_id = pb.id
                        ORDER BY ms.created_at DESC
                        LIMIT 1
                    ) ms ON TRUE
                    WHERE tp.execution_grade IN ('B', 'B+', 'C')
                       OR tp.action = 'NO_TRADE_WAIT_CONTEXT'
                       OR tp.pressure_status = 'WATCHLIST_PRESSURE'
                    ORDER BY tp.created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            else:
                await cur.execute(
                    """
                    SELECT tp.*, pb.start_wita AS signal_start_wita,
                           pb.end_wita AS signal_end_wita,
                           pb.duration_minutes, pb.event_count,
                           pb.density_per_minute,
                           ms.h4_structure,
                           ms.h4_context_type
                    FROM trade_plans tp
                    LEFT JOIN pressure_blocks pb ON tp.block_id = pb.id
                    LEFT JOIN LATERAL (
                        SELECT h4_structure, h4_context_type
                        FROM market_snapshots ms
                        WHERE ms.block_id = pb.id
                        ORDER BY ms.created_at DESC
                        LIMIT 1
                    ) ms ON TRUE
                    ORDER BY tp.created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            return await cur.fetchall()

    async def get_latest_watchlist_signals(self, limit: int = 20) -> list[dict]:
        return await self.get_latest_signals(limit=limit, bucket="watchlist")

    async def get_latest_signals(
        self,
        limit: int = 50,
        bucket: str = "watchlist",
    ) -> list[dict]:
        normalized_bucket = bucket.lower()
        if normalized_bucket not in {
            "all",
            "failed",
            "radar",
            "watchlist",
            "ready",
            "highlighted",
            "priority",
            "actionable",
        }:
            normalized_bucket = "all"
        fetch_limit = max(limit * 20, 100)

        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT
                    tp.id,
                    tp.id AS trade_plan_id,
                    pb.id AS block_id,
                    pb.symbol,
                    pb.start_utc,
                    pb.end_utc,
                    pb.start_wita AS signal_start_wita,
                    pb.end_wita AS signal_end_wita,
                    pb.duration_minutes,
                    pb.event_count,
                    pb.density_per_minute,
                    pb.max_gap_seconds,
                    pb.avg_gap_seconds,
                    pb.pressure_grade,
                    pb.pressure_status,
                    pb.finalize_mode,
                    pb.block_mode,
                    pb.pressure_temperature,
                    pb.wave_count,
                    pb.interrupted_by,
                    pb.theme_cluster,
                    pb.is_active,
                    tp.execution_grade,
                    tp.execution_side,
                    ms.h4_structure,
                    ms.h4_context_type,
                    COALESCE(tp.chart_phase, ms.chart_phase) AS chart_phase,
                    COALESCE(
                        tp.reason_code,
                        pb.pending_reason,
                        CASE
                            WHEN pb.pressure_grade NOT IN ('B+', 'A-', 'A', 'A+') THEN 'PRESSURE_BELOW_BPLUS'
                            WHEN tp.id IS NULL THEN 'TRADE_PLAN_REQUIRED'
                            ELSE 'UNCLASSIFIED'
                        END
                    ) AS reason_code,
                    tp.action,
                    tp.entry_zone,
                    tp.invalidation,
                    tp.message,
                    tp.signal_bucket,
                    tp.pressure_status AS trade_plan_pressure_status,
                    CASE
                        WHEN pb.pressure_grade IN ('B+', 'A-', 'A', 'A+') AND tp.id IS NOT NULL THEN 'READY'
                        WHEN pb.pressure_grade IN ('B+', 'A-', 'A', 'A+') THEN COALESCE(pb.trade_plan_status, 'TRADE_PLAN_REQUIRED')
                        ELSE 'NOT_REQUIRED'
                    END AS trade_plan_status,
                    CASE
                        WHEN pb.pressure_grade IN ('B+', 'A-', 'A', 'A+') AND tp.id IS NOT NULL THEN 'READY'
                        WHEN pb.pressure_grade IN ('B+', 'A-', 'A', 'A+') THEN COALESCE(pb.market_context_status, 'PENDING_OR_FAILED')
                        ELSE 'NOT_REQUIRED'
                    END AS market_context_status,
                    pb.pending_reason,
                    CASE
                        WHEN pb.pressure_grade = 'FAILED_MIN_DURATION' THEN 'failed'
                        WHEN pb.pressure_grade NOT IN ('B+', 'A-', 'A', 'A+') THEN 'radar_below_threshold'
                        WHEN tp.id IS NULL THEN 'watchlist_trade_plan_pending'
                        ELSE 'trade_plan_ready'
                    END AS dashboard_bucket,
                    CASE
                        WHEN pb.pressure_grade IN ('A', 'A+') AND tp.id IS NOT NULL THEN 'YES'
                        WHEN pb.pressure_grade IN ('B+', 'A-') AND tp.id IS NOT NULL THEN 'OPTIONAL'
                        WHEN pb.pressure_grade IN ('B+', 'A-', 'A', 'A+') THEN 'PENDING'
                        ELSE 'NO'
                    END AS owner_alert,
                    CASE
                        WHEN pb.pressure_grade = 'FAILED_MIN_DURATION' THEN
                            pb.symbol || ' pressure failed minimum duration: ' || ROUND(pb.duration_minutes::numeric, 2) || 'm < ' || %s || 'm.'
                        WHEN pb.pressure_grade NOT IN ('B+', 'A-', 'A', 'A+') AND pb.duration_minutes < %s THEN
                            pb.symbol || ' ' || pb.pressure_grade || ' pressure is below threshold. Duration ' || ROUND(pb.duration_minutes::numeric, 2) || 'm is below minimum radar threshold ' || %s || 'm.'
                        WHEN pb.pressure_grade NOT IN ('B+', 'A-', 'A', 'A+') THEN
                            pb.symbol || ' ' || pb.pressure_grade || ' pressure is below B+. Visible as radar only, not yet eligible for trade-plan processing.'
                        WHEN tp.id IS NULL AND pb.pending_reason IS NOT NULL THEN
                            pb.symbol || ' ' || pb.pressure_grade || ' trade plan pending: ' || pb.pending_reason
                        WHEN tp.id IS NULL THEN
                            pb.symbol || ' ' || pb.pressure_grade || ' pressure is valid. Trade plan is required and still pending market-context enrichment.'
                        ELSE COALESCE(tp.message, pb.symbol || ' ' || pb.pressure_grade || ' pressure has a ready trade plan.')
                    END AS display_message,
                    CASE
                        WHEN pb.pressure_grade IN ('B+', 'A-', 'A', 'A+') THEN TRUE
                        ELSE FALSE
                    END AS trade_plan_required
                FROM pressure_blocks pb
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM trade_plans tp
                    WHERE tp.block_id = pb.id
                    ORDER BY tp.created_at DESC
                    LIMIT 1
                ) tp ON TRUE
                LEFT JOIN LATERAL (
                    SELECT chart_phase, h4_structure, h4_context_type
                    FROM market_snapshots ms
                    WHERE ms.block_id = pb.id
                    ORDER BY ms.created_at DESC
                    LIMIT 1
                ) ms ON TRUE
                ORDER BY pb.end_utc DESC, pb.id DESC
                LIMIT %s
                """,
                (
                    settings.min_radar_minutes,  # FAILED_MIN_DURATION threshold display
                    settings.min_radar_minutes,
                    settings.min_radar_minutes,
                    fetch_limit,
                ),
            )
            rows = await cur.fetchall()
            return _select_latest_signal_rows(rows, bucket=normalized_bucket, limit=limit)

    async def get_trade_plan(self, plan_id: int) -> dict | None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT tp.*, pb.*,
                       tp.id AS trade_plan_id,
                       pb.id AS block_id,
                       ms.h4_structure,
                       ms.h4_context_type
                FROM trade_plans tp
                LEFT JOIN pressure_blocks pb ON tp.block_id = pb.id
                LEFT JOIN LATERAL (
                    SELECT h4_structure, h4_context_type
                    FROM market_snapshots ms
                    WHERE ms.block_id = pb.id
                    ORDER BY ms.created_at DESC
                    LIMIT 1
                ) ms ON TRUE
                WHERE tp.id = %s
                """,
                (plan_id,),
            )
            row = await cur.fetchone()
            return _with_density_metadata(row) if row else None

    async def get_trade_plan_for_block(self, block_id: int) -> dict | None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM trade_plans
                WHERE block_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (block_id,),
            )
            return await cur.fetchone()

    # ----- dashboard stats -----

    async def get_dashboard_stats(self) -> dict:
        async with get_cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM pressure_blocks WHERE is_active = TRUE"
            )
            active_row = await cur.fetchone()
            active = active_row["cnt"] if active_row else 0

            await cur.execute(
                """
                SELECT COUNT(*) AS cnt FROM pressure_blocks
                WHERE end_utc > NOW() - INTERVAL '24 hours'
                  AND duration_minutes >= %s
                """,
                (settings.min_radar_minutes,),
            )
            priority_row = await cur.fetchone()
            priority = priority_row["cnt"] if priority_row else 0

            await cur.execute(
                """
                SELECT COALESCE(ROUND(AVG(density_per_minute)::numeric, 2), 0) AS avg_d
                FROM pressure_blocks
                WHERE created_at > NOW() - INTERVAL '24 hours'
                """
            )
            avg_row = await cur.fetchone()
            avg_density = str(avg_row["avg_d"]) if avg_row else "0"

            await cur.execute(
                """
                SELECT MAX(end_utc) AS last_update FROM pressure_blocks
                """
            )
            row = await cur.fetchone()
            last = row["last_update"] if row else None
            last_str = last.strftime("%Y-%m-%d %H:%M UTC") if last else "-"

            return {
                "active_blocks": active,
                "priority_signals": priority,
                "avg_density": avg_density,
                "last_update": last_str,
            }

    async def get_today_signal_debug_counts(
        self,
        *,
        start_utc: datetime,
        end_utc: datetime,
    ) -> dict:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT
                    COUNT(*) AS signal_events_today,
                    COUNT(*) FILTER (WHERE source_service = %s) AS engine_source_events_today,
                    MAX(timestamp_utc) AS latest_signal_event_utc
                FROM signal_events
                WHERE timestamp_utc >= %s AND timestamp_utc < %s
                """,
                (settings.engine_log_source_service, start_utc, end_utc),
            )
            signal_row = await cur.fetchone() or {}

            await cur.execute(
                """
                SELECT
                    COUNT(*) AS engine_raw_logs_today,
                    COUNT(*) FILTER (
                        WHERE is_signalthrottle = TRUE
                          AND parse_status = 'SIGNALTHROTTLE_VALID'
                    ) AS raw_signalthrottle_valid_today
                FROM engine_log_entries
                WHERE timestamp_utc >= %s AND timestamp_utc < %s
                """,
                (start_utc, end_utc),
            )
            raw_row = await cur.fetchone() or {}

            await cur.execute(
                """
                SELECT COUNT(*) AS active_blocks_today
                FROM pressure_blocks
                WHERE end_utc >= %s AND end_utc < %s AND is_active = TRUE
                """,
                (start_utc, end_utc),
            )
            active_row = await cur.fetchone() or {}

            await cur.execute(
                """
                SELECT COUNT(*) AS dashboard_signals_today
                FROM pressure_blocks
                WHERE end_utc >= %s AND end_utc < %s
                  AND pressure_grade IN ('B+', 'A-', 'A', 'A+')
                """,
                (start_utc, end_utc),
            )
            dashboard_row = await cur.fetchone() or {}

            latest_event = signal_row.get("latest_signal_event_utc")
            return {
                "signal_events_today": int(signal_row.get("signal_events_today") or 0),
                "engine_source_events_today": int(signal_row.get("engine_source_events_today") or 0),
                "engine_raw_logs_today": int(raw_row.get("engine_raw_logs_today") or 0),
                "raw_signalthrottle_valid_today": int(raw_row.get("raw_signalthrottle_valid_today") or 0),
                "active_blocks_today": int(active_row.get("active_blocks_today") or 0),
                "dashboard_signals_today": int(dashboard_row.get("dashboard_signals_today") or 0),
                "latest_signal_event_utc": latest_event.isoformat() if latest_event else None,
            }

    async def get_engine_logs_daily_summary(
        self,
        *,
        start_utc: datetime,
        end_utc: datetime,
    ) -> dict[str, Any]:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT
                    COUNT(*) AS total_engine_logs,
                    COUNT(*) FILTER (
                        WHERE is_signalthrottle = TRUE
                          AND parse_status = 'SIGNALTHROTTLE_VALID'
                    ) AS signalthrottle_valid,
                    COUNT(*) FILTER (
                        WHERE parse_status IN (
                            'SIGNALTHROTTLE_PARSE_FAILED',
                            'SIGNALTHROTTLE_MISSING_TIMESTAMP'
                        )
                    ) AS signalthrottle_invalid,
                    COUNT(*) FILTER (
                        WHERE COALESCE(is_signalthrottle, FALSE) = FALSE
                          AND COALESCE(parse_status, '') NOT LIKE 'SIGNALTHROTTLE%%'
                    ) AS non_signalthrottle_logs,
                    MIN(timestamp_utc) AS first_raw_log_utc,
                    MAX(timestamp_utc) AS last_raw_log_utc
                FROM engine_log_entries
                WHERE timestamp_utc >= %s AND timestamp_utc < %s
                """,
                (start_utc, end_utc),
            )
            raw_totals = await cur.fetchone() or {}

            await cur.execute(
                """
                SELECT
                    COUNT(*) AS parsed_signal_events,
                    COUNT(*) FILTER (
                        WHERE COALESCE(meta->>'source_path', 'unknown') = 'engine_log_sync'
                    ) AS sync_events,
                    COUNT(*) FILTER (
                        WHERE COALESCE(meta->>'source_path', 'unknown') = 'webhook'
                    ) AS webhook_events,
                    COUNT(*) FILTER (
                        WHERE source_service = %s
                    ) AS engine_labeled_events,
                    MIN(timestamp_utc) AS first_signal_event_utc,
                    MAX(timestamp_utc) AS last_signal_event_utc
                FROM signal_events
                WHERE timestamp_utc >= %s AND timestamp_utc < %s
                """,
                (settings.engine_log_source_service, start_utc, end_utc),
            )
            signal_totals = await cur.fetchone() or {}

            await cur.execute(
                """
                SELECT COUNT(*) AS promoted_pressure_blocks
                FROM pressure_blocks
                WHERE end_utc >= %s AND end_utc < %s
                """,
                (start_utc, end_utc),
            )
            promoted_row = await cur.fetchone() or {}

            await cur.execute(
                """
                SELECT COUNT(*) AS dashboard_signals
                FROM pressure_blocks
                WHERE end_utc >= %s AND end_utc < %s
                  AND pressure_grade IN ('B+', 'A-', 'A', 'A+')
                """,
                (start_utc, end_utc),
            )
            dashboard_row = await cur.fetchone() or {}

            await cur.execute(
                """
                SELECT
                    symbol,
                    COUNT(*) AS event_count,
                    MIN(timestamp_utc) AS first_event_utc,
                    MAX(timestamp_utc) AS last_event_utc,
                    COUNT(*) FILTER (
                        WHERE COALESCE(meta->>'source_path', 'unknown') = 'engine_log_sync'
                    ) AS sync_event_count,
                    COUNT(*) FILTER (
                        WHERE COALESCE(meta->>'source_path', 'unknown') = 'webhook'
                    ) AS webhook_event_count,
                    COUNT(*) FILTER (
                        WHERE source_service = %s
                    ) AS engine_labeled_event_count
                FROM signal_events
                WHERE timestamp_utc >= %s AND timestamp_utc < %s
                GROUP BY symbol
                ORDER BY event_count DESC, symbol ASC
                """,
                (settings.engine_log_source_service, start_utc, end_utc),
            )
            symbol_rows = await cur.fetchall()

            await cur.execute(
                """
                SELECT
                    symbol,
                    COUNT(*) AS promoted_blocks,
                    MAX(pressure_grade) AS best_candidate_grade
                FROM pressure_blocks
                WHERE end_utc >= %s AND end_utc < %s
                GROUP BY symbol
                """,
                (start_utc, end_utc),
            )
            promoted_rows = await cur.fetchall()

            await cur.execute(
                """
                SELECT symbol, event_type, timestamp_utc, timestamp_wita,
                       chart_time, raw_message, source_service
                FROM signal_events
                WHERE timestamp_utc >= %s AND timestamp_utc < %s
                ORDER BY timestamp_utc ASC, id ASC
                """,
                (start_utc, end_utc),
            )
            event_rows = await cur.fetchall()

        promoted_by_symbol = {
            row["symbol"]: row
            for row in promoted_rows
            if row.get("symbol")
        }
        symbols: list[dict[str, Any]] = []
        for row in symbol_rows:
            symbol = row.get("symbol")
            if not symbol:
                continue
            promoted = promoted_by_symbol.get(symbol, {})
            promoted_blocks = int(promoted.get("promoted_blocks") or 0)
            symbols.append(
                {
                    "symbol": symbol,
                    "event_count": int(row.get("event_count") or 0),
                    "first_event_utc": row.get("first_event_utc").isoformat() if row.get("first_event_utc") else None,
                    "last_event_utc": row.get("last_event_utc").isoformat() if row.get("last_event_utc") else None,
                    "theme_cluster": classify_theme_cluster(symbol),
                    "sync_event_count": int(row.get("sync_event_count") or 0),
                    "webhook_event_count": int(row.get("webhook_event_count") or 0),
                    "engine_labeled_event_count": int(row.get("engine_labeled_event_count") or 0),
                    "promoted_blocks": promoted_blocks,
                    "best_candidate_grade": promoted.get("best_candidate_grade"),
                    "failure_reason": _engine_logs_failure_reason(
                        event_count=int(row.get("event_count") or 0),
                        promoted_blocks=promoted_blocks,
                    ),
                }
            )

        events = [
            LogEvent(
                symbol=row["symbol"],
                event_type=row["event_type"],
                timestamp_utc=row["timestamp_utc"],
                timestamp_wita=row.get("timestamp_wita"),
                chart_time=row.get("chart_time"),
                raw_message=row["raw_message"],
                source_service=row.get("source_service") or settings.engine_log_source_service,
            )
            for row in event_rows
        ]
        sequences = build_canonical_sequences(events, max_gap_seconds=None)
        clean_runs: list[dict[str, Any]] = []
        wave_counts: dict[str, int] = {}
        for index, seq_events in enumerate(sequences):
            if not seq_events:
                continue
            symbol = seq_events[0].symbol
            wave_counts[symbol] = wave_counts.get(symbol, 0) + 1
            metrics = calculate_pressure_metrics(seq_events)
            interrupted_by = (
                sequences[index + 1][0].symbol
                if index + 1 < len(sequences) and sequences[index + 1]
                else None
            )
            status = phase1_signal_status(
                duration_minutes=metrics["duration_minutes"],
                event_count=metrics["event_count"],
                density_per_minute=metrics["density_per_minute"],
            )
            run = {
                "symbol": symbol,
                "start_utc": seq_events[0].timestamp_utc.isoformat(),
                "end_utc": seq_events[-1].timestamp_utc.isoformat(),
                "start_wita": to_wita(seq_events[0].timestamp_utc),
                "end_wita": to_wita(seq_events[-1].timestamp_utc),
                "event_count": metrics["event_count"],
                "duration_minutes": metrics["duration_minutes"],
                "density_per_minute": metrics["density_per_minute"],
                "avg_gap_seconds": metrics["avg_gap_seconds"],
                "max_gap_seconds": metrics["max_gap_seconds"],
                "block_mode": "SAME_PAIR_SEQUENCE",
                "pressure_temperature": classify_pressure_temperature(metrics["density_per_minute"]),
                "wave_count": wave_counts[symbol],
                "interrupted_by": interrupted_by,
                "theme_cluster": classify_theme_cluster(symbol),
                "status": status,
            }
            if float(metrics["duration_minutes"] or 0) >= settings.min_radar_minutes:
                clean_runs.append(run)

        clean_runs.sort(
            key=lambda row: (
                float(row.get("duration_minutes") or 0),
                int(row.get("event_count") or 0),
            ),
            reverse=True,
        )
        priority_runs = sorted(
            [
                run
                for run in clean_runs
                if run.get("status") in {"PRIORITY_SIGNAL", "PRIORITY_CONTEXTUAL", "SUSTAINED_RADAR"}
            ],
            key=lambda row: (
                row.get("status") == "PRIORITY_SIGNAL",
                row.get("end_utc") or "",
                int(row.get("event_count") or 0),
            ),
            reverse=True,
        )
        themes = _build_theme_summary(symbols)

        parsed_signal_events = int(signal_totals.get("parsed_signal_events") or 0)
        total_engine_logs = int(raw_totals.get("total_engine_logs") or 0)
        raw_extracted_logs = total_engine_logs if total_engine_logs else parsed_signal_events

        return {
            "total_engine_logs": total_engine_logs,
            "raw_extracted_logs": raw_extracted_logs,
            "parsed_signal_events": parsed_signal_events,
            "signalthrottle_valid": int(raw_totals.get("signalthrottle_valid") or parsed_signal_events),
            "signalthrottle_invalid": int(raw_totals.get("signalthrottle_invalid") or 0),
            "non_signalthrottle_logs": int(raw_totals.get("non_signalthrottle_logs") or 0),
            "sync_events": int(signal_totals.get("sync_events") or 0),
            "webhook_events": int(signal_totals.get("webhook_events") or 0),
            "engine_labeled_events": int(signal_totals.get("engine_labeled_events") or 0),
            "first_raw_log_utc": (
                raw_totals.get("first_raw_log_utc").isoformat()
                if raw_totals.get("first_raw_log_utc")
                else None
            ),
            "last_raw_log_utc": (
                raw_totals.get("last_raw_log_utc").isoformat()
                if raw_totals.get("last_raw_log_utc")
                else None
            ),
            "first_signal_event_utc": (
                signal_totals.get("first_signal_event_utc").isoformat()
                if signal_totals.get("first_signal_event_utc")
                else None
            ),
            "last_signal_event_utc": (
                signal_totals.get("last_signal_event_utc").isoformat()
                if signal_totals.get("last_signal_event_utc")
                else None
            ),
            "promoted_pressure_blocks": int(promoted_row.get("promoted_pressure_blocks") or 0),
            "dashboard_signals": int(dashboard_row.get("dashboard_signals") or 0),
            "total_pairs": len(symbols),
            "consecutive_runs": len(sequences),
            "runs_ge_5m": len(clean_runs),
            "clean_runs": clean_runs[:50],
            "priority_runs": priority_runs[:10],
            "themes": themes,
            "symbols": symbols,
        }

    # ----- market_snapshots -----

    async def insert_market_snapshot(self, snapshot: dict) -> int:
        async with get_cursor() as cur:
            await cur.execute(
                """
                INSERT INTO market_snapshots
                    (block_id, symbol, signal_start_utc, signal_end_utc,
                     price_at_start, price_at_end, spread_points,
                     range_low, range_high, pivot_mid,
                     reclaim_level, breakdown_level, breakout_level,
                     d1_bias, h4_structure, h4_context_type, h1_phase, m15_phase,
                     chart_bias, chart_phase,
                     support_zone, resistance_zone,
                     nearest_supply_zone, nearest_demand_zone,
                     key_level, raw_ohlc)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                RETURNING id
                """,
                (
                    snapshot.get("block_id"),
                    snapshot["symbol"],
                    snapshot.get("signal_start_utc"),
                    snapshot.get("signal_end_utc"),
                    snapshot.get("price_at_start"),
                    snapshot.get("price_at_end"),
                    snapshot.get("spread_points"),
                    snapshot.get("range_low"),
                    snapshot.get("range_high"),
                    snapshot.get("pivot_mid"),
                    snapshot.get("reclaim_level"),
                    snapshot.get("breakdown_level"),
                    snapshot.get("breakout_level"),
                    snapshot.get("d1_bias"),
                    snapshot.get("h4_structure"),
                    snapshot.get("h4_context_type"),
                    snapshot.get("h1_phase"),
                    snapshot.get("m15_phase"),
                    snapshot.get("chart_bias"),
                    snapshot.get("chart_phase"),
                    snapshot.get("support_zone"),
                    snapshot.get("resistance_zone"),
                    snapshot.get("nearest_supply_zone"),
                    snapshot.get("nearest_demand_zone"),
                    snapshot.get("key_level"),
                    _json_or_none(snapshot.get("raw_ohlc")),
                ),
            )
            row = await cur.fetchone()
            assert row is not None
            return row["id"]

    # ----- signal_outcomes (Phase 4) -----

    async def get_trade_plans_without_outcome(self, limit: int = 20) -> list[dict]:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT tp.*,
                       pb.end_utc AS signal_end_utc,
                       ms.chart_phase AS chart_phase,
                      ms.price_at_end AS price_at_end,
                      ms.h4_context_type AS h4_context_type
                FROM trade_plans tp
                LEFT JOIN signal_outcomes so
                  ON so.trade_plan_id = tp.id
                LEFT JOIN pressure_blocks pb
                  ON pb.id = tp.block_id
                LEFT JOIN LATERAL (
                    SELECT chart_phase, price_at_end, h4_context_type
                    FROM market_snapshots
                    WHERE market_snapshots.block_id = tp.block_id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) ms ON TRUE
                WHERE so.id IS NULL
                ORDER BY tp.created_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            return await cur.fetchall()

    async def upsert_signal_outcome(
        self,
        trade_plan_id: int,
        result: dict[str, Any],
    ) -> int:
        params = {
            "trade_plan_id": trade_plan_id,
            "symbol": result.get("symbol"),
            "pressure_grade": result.get("pressure_grade"),
            "execution_grade": result.get("execution_grade"),
            "chart_phase": result.get("chart_phase"),
            "h4_context_type": result.get("h4_context_type"),
            "execution_side": result.get("execution_side"),
            "signal_end_utc": result.get("signal_end_utc"),
            "price_at_signal": result.get("price_at_signal"),
            "price_after_15m": result.get("price_after_15m"),
            "price_after_30m": result.get("price_after_30m"),
            "price_after_60m": result.get("price_after_60m"),
            "mfe_15m": result.get("mfe_15m"),
            "mae_15m": result.get("mae_15m"),
            "mfe_30m": result.get("mfe_30m"),
            "mae_30m": result.get("mae_30m"),
            "mfe_60m": result.get("mfe_60m"),
            "mae_60m": result.get("mae_60m"),
            "result_label": result.get("result_label"),
            "raw_result": _json_or_none(result.get("raw_result") or {}),
        }

        async with get_cursor() as cur:
            await cur.execute(
                """
                INSERT INTO signal_outcomes (
                    trade_plan_id, symbol, pressure_grade, execution_grade,
                    chart_phase, h4_context_type, execution_side, signal_end_utc, price_at_signal,
                    price_after_15m, price_after_30m, price_after_60m,
                    mfe_15m, mae_15m, mfe_30m, mae_30m, mfe_60m, mae_60m,
                    result_label, raw_result, updated_at
                )
                VALUES (
                    %(trade_plan_id)s, %(symbol)s, %(pressure_grade)s, %(execution_grade)s,
                    %(chart_phase)s, %(h4_context_type)s, %(execution_side)s, %(signal_end_utc)s, %(price_at_signal)s,
                    %(price_after_15m)s, %(price_after_30m)s, %(price_after_60m)s,
                    %(mfe_15m)s, %(mae_15m)s, %(mfe_30m)s, %(mae_30m)s, %(mfe_60m)s, %(mae_60m)s,
                    %(result_label)s, %(raw_result)s::jsonb, NOW()
                )
                ON CONFLICT (trade_plan_id) DO UPDATE SET
                    symbol = EXCLUDED.symbol,
                    pressure_grade = EXCLUDED.pressure_grade,
                    execution_grade = EXCLUDED.execution_grade,
                    chart_phase = EXCLUDED.chart_phase,
                    h4_context_type = EXCLUDED.h4_context_type,
                    execution_side = EXCLUDED.execution_side,
                    signal_end_utc = EXCLUDED.signal_end_utc,
                    price_at_signal = EXCLUDED.price_at_signal,
                    price_after_15m = EXCLUDED.price_after_15m,
                    price_after_30m = EXCLUDED.price_after_30m,
                    price_after_60m = EXCLUDED.price_after_60m,
                    mfe_15m = EXCLUDED.mfe_15m,
                    mae_15m = EXCLUDED.mae_15m,
                    mfe_30m = EXCLUDED.mfe_30m,
                    mae_30m = EXCLUDED.mae_30m,
                    mfe_60m = EXCLUDED.mfe_60m,
                    mae_60m = EXCLUDED.mae_60m,
                    result_label = EXCLUDED.result_label,
                    raw_result = EXCLUDED.raw_result,
                    updated_at = NOW()
                RETURNING id
                """,
                params,
            )
            row = await cur.fetchone()
            assert row is not None
            return row["id"]

    async def get_latest_outcomes(self, limit: int = 20) -> list[dict]:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT so.*, tp.action
                FROM signal_outcomes so
                LEFT JOIN trade_plans tp ON tp.id = so.trade_plan_id
                ORDER BY so.signal_end_utc DESC NULLS LAST, so.created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return await cur.fetchall()

    async def get_outcome(self, outcome_id: int) -> dict | None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT so.*, tp.action
                FROM signal_outcomes so
                LEFT JOIN trade_plans tp ON tp.id = so.trade_plan_id
                WHERE so.id = %s
                """,
                (outcome_id,),
            )
            return await cur.fetchone()

    async def get_outcome_summary(self) -> dict:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE result_label = 'FOLLOW_THROUGH_STRONG') AS strong_count,
                    AVG(mfe_30m) AS avg_mfe_30m,
                    AVG(mae_30m) AS avg_mae_30m
                FROM signal_outcomes
                """
            )
            row = await cur.fetchone() or {}
            total = int(row.get("total") or 0)
            strong = int(row.get("strong_count") or 0)
            strong_pct = (strong / total * 100.0) if total else 0.0

            await cur.execute(
                """
                SELECT chart_phase,
                       COUNT(*) AS cnt,
                       COUNT(*) FILTER (WHERE result_label = 'FOLLOW_THROUGH_STRONG') AS strong
                FROM signal_outcomes
                WHERE chart_phase IS NOT NULL
                GROUP BY chart_phase
                """
            )
            phase_rows = await cur.fetchall()

            await cur.execute(
                """
                SELECT h4_context_type,
                       COUNT(*) AS cnt,
                       COUNT(*) FILTER (WHERE result_label = 'FOLLOW_THROUGH_STRONG') AS strong
                FROM signal_outcomes
                WHERE h4_context_type IS NOT NULL
                GROUP BY h4_context_type
                """
            )
            h4_context_rows = await cur.fetchall()

            best_phase = None
            worst_phase = None
            best_pct = -1.0
            worst_pct = 101.0
            for r in phase_rows:
                cnt = int(r.get("cnt") or 0)
                if cnt < 3:
                    continue
                pct = (int(r.get("strong") or 0) / cnt) * 100.0
                if pct > best_pct:
                    best_pct = pct
                    best_phase = r.get("chart_phase")
                if pct < worst_pct:
                    worst_pct = pct
                    worst_phase = r.get("chart_phase")

            best_h4_context_type = None
            worst_h4_context_type = None
            best_h4_pct = -1.0
            worst_h4_pct = 101.0
            for r in h4_context_rows:
                cnt = int(r.get("cnt") or 0)
                if cnt < 3:
                    continue
                pct = (int(r.get("strong") or 0) / cnt) * 100.0
                if pct > best_h4_pct:
                    best_h4_pct = pct
                    best_h4_context_type = r.get("h4_context_type")
                if pct < worst_h4_pct:
                    worst_h4_pct = pct
                    worst_h4_context_type = r.get("h4_context_type")

            return {
                "total": total,
                "strong_pct": round(strong_pct, 2),
                "avg_mfe_30m": float(row.get("avg_mfe_30m") or 0),
                "avg_mae_30m": float(row.get("avg_mae_30m") or 0),
                "best_phase": best_phase,
                "worst_phase": worst_phase,
                "best_h4_context_type": best_h4_context_type,
                "worst_h4_context_type": worst_h4_context_type,
            }

    async def get_outcomes_by_phase(self) -> list[dict]:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT chart_phase,
                       COUNT(*) AS count,
                       COUNT(*) FILTER (WHERE result_label = 'FOLLOW_THROUGH_STRONG') AS strong_count,
                       AVG(mfe_30m) AS avg_mfe_30m,
                       AVG(mae_30m) AS avg_mae_30m
                FROM signal_outcomes
                WHERE chart_phase IS NOT NULL
                GROUP BY chart_phase
                ORDER BY count DESC
                """
            )
            rows = await cur.fetchall()
            return [_phase_grade_row(r, key="chart_phase") for r in rows]

    async def get_outcomes_by_h4_context_type(self) -> list[dict]:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT h4_context_type,
                       COUNT(*) AS count,
                       COUNT(*) FILTER (WHERE result_label = 'FOLLOW_THROUGH_STRONG') AS strong_count,
                       AVG(mfe_30m) AS avg_mfe_30m,
                       AVG(mae_30m) AS avg_mae_30m
                FROM signal_outcomes
                WHERE h4_context_type IS NOT NULL
                GROUP BY h4_context_type
                ORDER BY count DESC
                """
            )
            rows = await cur.fetchall()
            return [_phase_grade_row(r, key="h4_context_type") for r in rows]

    async def get_outcomes_by_reason_code(self) -> list[dict]:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT COALESCE(
                           tp.reason_code,
                           so.raw_result ->> 'reason_code'
                       ) AS reason_code,
                       COUNT(*) AS count,
                       COUNT(*) FILTER (WHERE so.result_label = 'FOLLOW_THROUGH_STRONG') AS strong_count,
                       AVG(so.mfe_30m) AS avg_mfe_30m,
                       AVG(so.mae_30m) AS avg_mae_30m
                FROM signal_outcomes so
                LEFT JOIN trade_plans tp ON tp.id = so.trade_plan_id
                WHERE COALESCE(
                          tp.reason_code,
                          so.raw_result ->> 'reason_code'
                      ) IS NOT NULL
                GROUP BY COALESCE(
                             tp.reason_code,
                             so.raw_result ->> 'reason_code'
                         )
                ORDER BY count DESC, reason_code ASC
                """
            )
            rows = await cur.fetchall()
            return [_phase_grade_row(r, key="reason_code") for r in rows]

    async def get_outcomes_by_grade(self) -> list[dict]:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT pressure_grade,
                       execution_grade,
                       COUNT(*) AS count,
                       COUNT(*) FILTER (WHERE result_label = 'FOLLOW_THROUGH_STRONG') AS strong_count,
                       AVG(mfe_30m) AS avg_mfe_30m,
                       AVG(mae_30m) AS avg_mae_30m
                FROM signal_outcomes
                GROUP BY pressure_grade, execution_grade
                ORDER BY count DESC
                """
            )
            rows = await cur.fetchall()
            return [_phase_grade_row(r) for r in rows]


def _phase_grade_row(row: dict, *, key: str | None = None) -> dict:
    count = int(row.get("count") or 0)
    strong = int(row.get("strong_count") or 0)
    strong_pct = (strong / count * 100.0) if count else 0.0
    out: dict[str, Any] = {
        "count": count,
        "strong_count": strong,
        "strong_pct": round(strong_pct, 2),
        "avg_mfe_30m": float(row.get("avg_mfe_30m") or 0),
        "avg_mae_30m": float(row.get("avg_mae_30m") or 0),
    }
    if key:
        out[key] = row.get(key)
    else:
        out["pressure_grade"] = row.get("pressure_grade")
        out["execution_grade"] = row.get("execution_grade")
    return out


def _select_latest_signal_rows(
    rows: list[dict],
    *,
    bucket: str,
    limit: int | None = None,
) -> list[dict]:
    collapsed = _select_latest_series_signal_rows(
        rows,
        merge_gap_seconds=settings.max_event_gap_seconds,
    )

    filtered = [row for row in collapsed if _matches_signal_bucket(row, bucket)]
    filtered = [_with_density_metadata(row) for row in filtered]
    if limit is None:
        return filtered
    return filtered[:limit]


def _select_latest_series_signal_rows(
    rows: list[dict],
    *,
    merge_gap_seconds: int,
) -> list[dict]:
    merged_series = _merge_pressure_series(rows, merge_gap_seconds=merge_gap_seconds)
    rows_by_block_id = {
        _row_block_id(row): row
        for row in rows
        if _row_block_id(row) is not None
    }

    series_rows: list[dict] = []
    for series in merged_series:
        latest_block_id = series.get("latest_block_id")
        if latest_block_id is None:
            continue
        representative = dict(rows_by_block_id.get(latest_block_id) or {})
        if not representative:
            continue
        representative.update(
            {
                "block_id": latest_block_id,
                "start_utc": series["start_utc"],
                "end_utc": series["end_utc"],
                "duration_minutes": series["duration_minutes"],
                "event_count": series["event_count"],
                "density_per_minute": series["density_per_minute"],
                "max_gap_seconds": series["max_gap_seconds"],
                "block_count": series["block_count"],
                "block_ids": series["block_ids"],
                "latest_block_id": latest_block_id,
                "latest_pressure_grade": series["latest_pressure_grade"],
                "best_pressure_grade": series["best_pressure_grade"],
                "best_valid_block_grade": series.get("best_valid_block_grade"),
                "series_reason": series.get("series_reason"),
            }
        )
        series_rows.append(representative)

    return series_rows


def _matches_signal_bucket(row: dict, bucket: str) -> bool:
    pressure_grade = row.get("pressure_grade")
    has_trade_plan = bool(row.get("trade_plan_id"))
    execution_grade = row.get("execution_grade")
    action = row.get("action") or ""
    valid_grades = {"B+", "A-", "A", "A+"}
    actionable_grades = {"B+", "A", "A+"}
    wait_actions = {"NO_TRADE", "NO_TRADE_WAIT_CONTEXT", "WAIT"}

    if bucket == "all":
        return True
    if bucket == "failed":
        return pressure_grade == "FAILED_MIN_DURATION"
    if bucket == "radar":
        # Radar = anything that did not promote to a valid trade-plan grade
        # but still represents real (not failed) pressure.
        return pressure_grade not in valid_grades and pressure_grade != "FAILED_MIN_DURATION"
    if bucket == "watchlist":
        return pressure_grade in valid_grades and not has_trade_plan
    if bucket == "ready":
        return pressure_grade in valid_grades and has_trade_plan
    if bucket == "highlighted":
        return pressure_grade in {"A-", "A", "A+"}
    if bucket == "priority":
        return pressure_grade in {"A", "A+"} and has_trade_plan
    if bucket == "actionable":
        return has_trade_plan and execution_grade in actionable_grades and action not in wait_actions
    return True


def _merge_pressure_series(
    rows: list[dict],
    *,
    merge_gap_seconds: int,
    limit: int | None = None,
) -> list[dict]:
    rows = _dedupe_exact_pressure_block_rows(rows)
    if not rows:
        return []

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row.get("symbol") or "",
            row.get("start_utc") or row.get("end_utc"),
            row.get("end_utc"),
            row.get("id") or row.get("block_id") or 0,
        ),
    )

    merged: list[dict] = []
    current: dict[str, Any] | None = None

    for row in sorted_rows:
        block_id = row.get("id") or row.get("block_id")
        start_utc = row.get("start_utc")
        end_utc = row.get("end_utc")
        if start_utc is None or end_utc is None:
            continue

        if current is None or row.get("symbol") != current.get("symbol"):
            if current is not None:
                merged.append(_finalize_pressure_series(current))
            current = _init_pressure_series(row, block_id)
            continue

        gap_seconds = (start_utc - current["end_utc"]).total_seconds()
        if gap_seconds <= merge_gap_seconds:
            current["start_utc"] = min(current["start_utc"], start_utc)
            current["end_utc"] = max(current["end_utc"], end_utc)
            current["max_gap_seconds"] = max(
                float(current.get("max_gap_seconds") or 0),
                float(row.get("max_gap_seconds") or 0),
                max(gap_seconds, 0),
            )
            if start_utc <= current["latest_end_utc"]:
                # Overlapping windows from replay are alternative reconstructions
                # of the same underlying pressure sequence. Keep the widest
                # coverage instead of double-counting events or surfacing
                # replay alternatives as separate raw-history blocks.
                current["event_count"] = max(
                    current["event_count"],
                    int(row.get("event_count") or 0),
                )
            else:
                current["block_count"] += 1
                current["block_ids"].append(block_id)
                current["event_count"] += int(row.get("event_count") or 0)
                if gap_seconds > settings.max_continuity_gap_seconds:
                    current["series_reason"] = "SPLIT_BY_CONTINUITY_GAP"
            if end_utc >= current["latest_end_utc"]:
                current["latest_end_utc"] = end_utc
                current["latest_block_id"] = block_id
                current["latest_pressure_grade"] = row.get("pressure_grade")
                current["pressure_status"] = row.get("pressure_status")
                current["finalize_mode"] = row.get("finalize_mode")
                current["is_active"] = row.get("is_active")
            current["best_pressure_grade"] = _better_pressure_grade(
                current.get("best_pressure_grade"),
                row.get("pressure_grade"),
            )
            current["best_valid_block_grade"] = _better_valid_pressure_grade(
                current.get("best_valid_block_grade"),
                row.get("pressure_grade"),
            )
            if row.get("finalize_mode") == "CONTINUITY_SPLIT":
                current["series_reason"] = "SPLIT_BY_CONTINUITY_GAP"
            continue

        merged.append(_finalize_pressure_series(current))
        current = _init_pressure_series(row, block_id)

    if current is not None:
        merged.append(_finalize_pressure_series(current))

    merged.sort(key=lambda row: (row.get("end_utc"), row.get("latest_block_id") or 0), reverse=True)
    if limit is None:
        return merged
    return merged[:limit]


def _init_pressure_series(row: dict, block_id: Any) -> dict[str, Any]:
    pressure_grade = row.get("pressure_grade")
    return {
        "symbol": row.get("symbol"),
        "start_utc": row.get("start_utc"),
        "end_utc": row.get("end_utc"),
        "latest_end_utc": row.get("end_utc"),
        "event_count": int(row.get("event_count") or 0),
        "block_count": 1,
        "block_ids": [block_id],
        "latest_block_id": block_id,
        "latest_pressure_grade": pressure_grade,
        "best_pressure_grade": pressure_grade,
        "best_valid_block_grade": pressure_grade if _is_valid_pressure_grade(pressure_grade) else None,
        "series_reason": (
            "SPLIT_BY_CONTINUITY_GAP"
            if row.get("finalize_mode") == "CONTINUITY_SPLIT"
            else "CONTINUOUS_PRESSURE_SERIES"
        ),
        "pressure_status": row.get("pressure_status"),
        "finalize_mode": row.get("finalize_mode"),
        "is_active": row.get("is_active"),
        "max_gap_seconds": float(row.get("max_gap_seconds") or 0),
    }


def _dedupe_exact_pressure_block_rows(rows: list[dict]) -> list[dict]:
    deduped: dict[tuple[Any, ...], dict] = {}
    for row in rows:
        key = _pressure_block_identity(row)
        existing = deduped.get(key)
        if existing is None or _pressure_block_order_key(row) > _pressure_block_order_key(existing):
            deduped[key] = row
    return list(deduped.values())


def _collapse_replay_overlap_block_rows(rows: list[dict]) -> list[dict]:
    ranked_rows = sorted(rows, key=_replay_block_preference_key, reverse=True)
    kept: list[dict] = []
    for row in ranked_rows:
        if any(_is_replay_overlap_duplicate(row, candidate) for candidate in kept):
            continue
        kept.append(row)
    return kept


def _is_replay_overlap_duplicate(row: dict, candidate: dict) -> bool:
    if not (_is_replay_row(row) and _is_replay_row(candidate)):
        return False
    if row.get("symbol") != candidate.get("symbol"):
        return False

    row_start = row.get("start_utc")
    row_end = row.get("end_utc")
    candidate_start = candidate.get("start_utc")
    candidate_end = candidate.get("end_utc")
    if not isinstance(row_start, datetime):
        return False
    if not isinstance(row_end, datetime):
        return False
    if not isinstance(candidate_start, datetime):
        return False
    if not isinstance(candidate_end, datetime):
        return False

    overlap_start = max(row_start, candidate_start)
    overlap_end = min(row_end, candidate_end)
    overlap_seconds = (overlap_end - overlap_start).total_seconds()
    if overlap_seconds <= 0:
        return False

    row_seconds = (row_end - row_start).total_seconds()
    candidate_seconds = (candidate_end - candidate_start).total_seconds()
    shorter_window = min(row_seconds, candidate_seconds)
    if shorter_window <= 0:
        return False

    return overlap_seconds / shorter_window >= 0.9


def _is_replay_row(row: dict) -> bool:
    return row.get("pressure_status") == "REPLAY" or row.get("finalize_mode") == "REPLAY_FINALIZE"


def _replay_block_preference_key(row: dict) -> tuple[Any, ...]:
    start_utc = row.get("start_utc")
    end_utc = row.get("end_utc")
    duration_seconds = 0.0
    if isinstance(start_utc, datetime) and isinstance(end_utc, datetime):
        duration_seconds = max((end_utc - start_utc).total_seconds(), 0.0)

    grade_rank = {"REJECT": 0, "C": 1, "B+": 2, "A-": 3, "A": 4, "A+": 5}
    pressure_grade = row.get("pressure_grade")
    pressure_grade_rank = grade_rank.get(pressure_grade, -1) if isinstance(pressure_grade, str) else -1

    return (
        1 if row.get("trade_plan_id") is not None else 0,
        duration_seconds,
        float(row.get("event_count") or 0),
        pressure_grade_rank,
        row.get("end_utc"),
        row.get("start_utc"),
        row.get("id") or row.get("block_id") or 0,
    )


def _pressure_block_identity(row: dict) -> tuple[Any, ...]:
    block_hash = row.get("block_hash")
    if block_hash:
        return ("block_hash", block_hash)
    return (
        "natural",
        row.get("symbol"),
        row.get("start_utc"),
        row.get("end_utc"),
        row.get("event_count"),
        row.get("duration_minutes"),
        row.get("pressure_grade"),
        row.get("pressure_status"),
        row.get("finalize_mode"),
    )


def _pressure_block_order_key(row: dict) -> tuple[Any, ...]:
    return (
        row.get("end_utc"),
        row.get("start_utc"),
        _row_block_id(row) or 0,
    )


def _row_block_id(row: dict) -> Any:
    return row.get("id") or row.get("block_id")


def _series_block_ids(series: dict[str, Any]) -> set[Any]:
    raw_ids = series.get("block_ids") or []
    if not isinstance(raw_ids, list):
        return set()
    return {block_id for block_id in raw_ids if block_id is not None}


def _finalize_pressure_series(series: dict[str, Any]) -> dict[str, Any]:
    start_utc = series["start_utc"]
    end_utc = series["end_utc"]
    duration_minutes = round((end_utc - start_utc).total_seconds() / 60.0, 2)
    density = round(series["event_count"] / duration_minutes, 2) if duration_minutes > 0 else 0.0
    return {
        "symbol": series["symbol"],
        "start_utc": start_utc,
        "end_utc": end_utc,
        "duration_minutes": duration_minutes,
        "event_count": series["event_count"],
        "density_per_minute": density,
        "max_gap_seconds": round(float(series.get("max_gap_seconds") or 0), 2),
        "block_count": series["block_count"],
        "block_ids": series["block_ids"],
        "latest_block_id": series["latest_block_id"],
        "latest_pressure_grade": series["latest_pressure_grade"],
        "best_pressure_grade": series["best_pressure_grade"],
        "best_valid_block_grade": series.get("best_valid_block_grade"),
        "series_reason": series.get("series_reason") or "CONTINUOUS_PRESSURE_SERIES",
        "pressure_status": series["pressure_status"],
        "finalize_mode": series["finalize_mode"],
        "is_active": series["is_active"],
    }


def _with_density_metadata(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    density = row.get("density_per_minute")
    try:
        density_value = float(density) if density is not None else None
    except (TypeError, ValueError):
        density_value = None
    out["density_state"] = _density_state(density_value)
    out["grade_note"] = _pressure_grade_note(
        pressure_grade=row.get("best_pressure_grade") or row.get("pressure_grade"),
        density_per_minute=density_value,
        duration_minutes=row.get("duration_minutes"),
        max_gap_seconds=row.get("max_gap_seconds"),
    )
    return out


def _with_series_metadata(row: dict[str, Any]) -> dict[str, Any]:
    out = _with_density_metadata(row)
    out["series_gap_rule_seconds"] = settings.max_event_gap_seconds
    out["block_continuity_rule_seconds"] = settings.max_continuity_gap_seconds
    return out


def _density_state(density: float | None) -> str:
    if density is None:
        return "UNKNOWN"
    if density >= 10:
        return "VERY_HIGH_DENSITY"
    if density >= 7:
        return "HIGH_DENSITY"
    if density >= 5:
        return "VALID_DENSITY"
    return "LOW_DENSITY"


def _pressure_grade_note(
    *,
    pressure_grade: Any,
    density_per_minute: float | None,
    duration_minutes: Any,
    max_gap_seconds: Any,
) -> str | None:
    try:
        duration_value = float(duration_minutes) if duration_minutes is not None else None
    except (TypeError, ValueError):
        duration_value = None

    try:
        gap_value = float(max_gap_seconds) if max_gap_seconds is not None else None
    except (TypeError, ValueError):
        gap_value = None

    if (
        pressure_grade == "B+"
        and density_per_minute is not None
        and density_per_minute >= 7
        and gap_value is not None
        and gap_value <= 60
        and duration_value is not None
        and duration_value < 10
    ):
        return "B+ strong density / A- candidate, but duration below 10m"

    if density_per_minute is not None and density_per_minute >= 10:
        return "Very high density pressure"

    if density_per_minute is not None and density_per_minute >= 7:
        return "High density pressure"

    return None


def _better_pressure_grade(current: Any, candidate: Any) -> Any:
    rank = {"REJECT": 0, "C": 1, "B+": 2, "A-": 3, "A": 4, "A+": 5}
    current_rank = rank.get(current, -1)
    candidate_rank = rank.get(candidate, -1)
    if candidate_rank >= current_rank:
        return candidate
    return current


def _is_valid_pressure_grade(pressure_grade: Any) -> bool:
    return pressure_grade in {"B+", "A-", "A", "A+"}


def _better_valid_pressure_grade(current: Any, candidate: Any) -> Any:
    if not _is_valid_pressure_grade(candidate):
        return current
    if not _is_valid_pressure_grade(current):
        return candidate
    return _better_pressure_grade(current, candidate)


def _engine_logs_failure_reason(*, event_count: int, promoted_blocks: int) -> str | None:
    if promoted_blocks > 0:
        return None
    if event_count <= 0:
        return "NO_EVENTS"
    return "PARSED_ONLY_NO_PROMOTION"


def _build_theme_summary(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    themes: dict[str, dict[str, Any]] = {}
    for row in symbols:
        cluster = row.get("theme_cluster") or classify_theme_cluster(row.get("symbol"))
        if not cluster:
            continue
        theme = themes.setdefault(
            cluster,
            {
                "theme_cluster": cluster,
                "event_count": 0,
                "members": [],
            },
        )
        event_count = int(row.get("event_count") or 0)
        theme["event_count"] += event_count
        theme["members"].append(
            {
                "symbol": row.get("symbol"),
                "event_count": event_count,
            }
        )

    output = []
    for theme in themes.values():
        members = sorted(theme["members"], key=lambda item: item["event_count"], reverse=True)
        output.append(
            {
                "theme_cluster": theme["theme_cluster"],
                "event_count": theme["event_count"],
                "leaders": [member["symbol"] for member in members[:3]],
                "members": members,
                "status": "THEME_ALERT" if theme["event_count"] >= 100 else "SUPPORTING_THEME",
            }
        )
    return sorted(output, key=lambda item: item["event_count"], reverse=True)


def _build_signal_throttle_states(events: list[LogEvent]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda item: item.timestamp_utc):
        parsed = parse_signalthrottle(
            raw_message=event.raw_message,
            timestamp_utc=event.timestamp_utc,
        )
        if parsed is None:
            continue

        current = states[-1] if states else None
        if current is None or not _can_extend_throttle_state(current, event):
            states.append(
                {
                    "symbol": parsed.symbol,
                    "state_start_utc": event.timestamp_utc,
                    "state_end_utc": event.timestamp_utc,
                    "window_seconds": parsed.window_seconds,
                    "count_threshold": parsed.count,
                    "log_count": 1,
                    "avg_gap_seconds": None,
                    "max_gap_seconds": None,
                    "duration_minutes": 0.0,
                }
            )
            continue

        previous_end = current["state_end_utc"]
        gap_seconds = max((event.timestamp_utc - previous_end).total_seconds(), 0.0)
        current["state_end_utc"] = event.timestamp_utc
        current["log_count"] += 1
        current["duration_minutes"] = round(
            max((event.timestamp_utc - current["state_start_utc"]).total_seconds(), 0.0) / 60.0,
            2,
        )
        current["max_gap_seconds"] = max(current["max_gap_seconds"] or 0.0, gap_seconds)

        total_gap_seconds = float(current.get("_total_gap_seconds") or 0.0) + gap_seconds
        current["_total_gap_seconds"] = total_gap_seconds
        if current["log_count"] > 1:
            current["avg_gap_seconds"] = round(total_gap_seconds / (current["log_count"] - 1), 2)

    for state in states:
        state.pop("_total_gap_seconds", None)
    return states


def _can_extend_throttle_state(state: dict[str, Any], event: LogEvent) -> bool:
    state_end_utc = state.get("state_end_utc")
    if not isinstance(state_end_utc, datetime):
        return False
    if state.get("symbol") != event.symbol:
        return False

    parsed = parse_signalthrottle(
        raw_message=event.raw_message,
        timestamp_utc=event.timestamp_utc,
    )
    if parsed is None:
        return False
    if state.get("count_threshold") != parsed.count:
        return False
    if state.get("window_seconds") != parsed.window_seconds:
        return False

    return (event.timestamp_utc - state_end_utc).total_seconds() <= parsed.window_seconds


def _json_or_none(obj: Any) -> str | None:
    if obj is None:
        return None
    import json
    return json.dumps(obj, default=str)
