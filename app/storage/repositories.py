from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..models.log_event import LogEvent
from ..parser.timestamp_mapper import to_chart_time, to_wita
from ..scoring.pressure_grader import grade_pressure
from ..scoring.pressure_metrics import calculate_pressure_metrics
from .postgres import get_cursor
from ..utils.json_utils import make_event_hash

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
                "SELECT id FROM signal_events WHERE event_hash = %s",
                (event_hash,),
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
    ) -> dict:
        effective_last_event_utc = last_event_utc or end_utc
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
                        finalize_mode, existing["id"],
                    ),
                )
                row = await cur.fetchone()
                assert row is not None
                return {
                    "id": row["id"],
                    "action": "updated",
                    "pressure_status": pressure_status,
                    "pressure_grade": pressure_grade,
                }
            else:
                await cur.execute(
                    """
                    INSERT INTO pressure_blocks
                        (symbol, start_utc, end_utc, start_wita, end_wita,
                         chart_start_time, chart_end_time, last_event_utc,
                         duration_minutes, event_count, density_per_minute,
                         avg_gap_seconds, max_gap_seconds,
                         pressure_grade, pressure_status, block_relation,
                         previous_block_id, finalize_mode, is_active)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
                    RETURNING id
                    """,
                    (
                        symbol, start_utc, end_utc, start_wita, end_wita,
                        chart_start_time, chart_end_time,
                        effective_last_event_utc,
                        duration_minutes, event_count, density_per_minute,
                        avg_gap_seconds, max_gap_seconds,
                        pressure_grade, pressure_status, block_relation,
                        previous_block_id, finalize_mode,
                    ),
                )
                row = await cur.fetchone()
                assert row is not None
                return {
                    "id": row["id"],
                    "action": "created",
                    "pressure_status": pressure_status,
                    "pressure_grade": pressure_grade,
                }

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

    async def upsert_live_block_from_event(
        self,
        event: LogEvent,
        *,
        max_event_gap_seconds: int,
        chart_offset_hours: int,
    ) -> dict:
        await self.mark_other_active_blocks_cooling(event.symbol)

        existing = await self.get_active_block(event.symbol)
        previous_block_id: int | None = None
        start_utc = event.timestamp_utc

        if existing:
            previous_block_id = existing.get("previous_block_id")
            gap_seconds = (event.timestamp_utc - existing["end_utc"]).total_seconds()
            if gap_seconds > max_event_gap_seconds:
                await self.mark_block_hard_finalized(existing["id"])
                existing = None
            else:
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
                """,
                (block_id,),
            )

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
                """,
                (block_id,),
            )

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
                """,
                (block_id,),
            )

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
        self, symbol: str | None = None, limit: int = 50
    ) -> list[dict]:
        async with get_cursor() as cur:
            if symbol:
                await cur.execute(
                    """
                    SELECT * FROM pressure_blocks
                    WHERE symbol = %s
                    ORDER BY end_utc DESC LIMIT %s
                    """,
                    (symbol, limit),
                )
            else:
                await cur.execute(
                    """
                    SELECT * FROM pressure_blocks
                    ORDER BY end_utc DESC LIMIT %s
                    """,
                    (limit,),
                )
            return await cur.fetchall()

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

    # ----- trade_plans -----

    async def insert_trade_plan(self, block_id: int, plan: dict) -> int:
        async with get_cursor() as cur:
            await cur.execute(
                """
                INSERT INTO trade_plans
                    (block_id, symbol, pressure_status, signal_bucket,
                     pressure_grade, execution_grade,
                     execution_side, action, entry_zone, breakout_level,
                     reclaim_level, invalidation, tp1, tp2, tp3,
                     message, payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
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
                           pb.density_per_minute
                    FROM trade_plans tp
                    LEFT JOIN pressure_blocks pb ON tp.block_id = pb.id
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
                           pb.density_per_minute
                    FROM trade_plans tp
                    LEFT JOIN pressure_blocks pb ON tp.block_id = pb.id
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
                           pb.density_per_minute
                    FROM trade_plans tp
                    LEFT JOIN pressure_blocks pb ON tp.block_id = pb.id
                    ORDER BY tp.created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            return await cur.fetchall()

    async def get_trade_plan(self, plan_id: int) -> dict | None:
        async with get_cursor() as cur:
            await cur.execute(
                """
                SELECT tp.*, pb.*,
                       tp.id AS trade_plan_id,
                       pb.id AS block_id
                FROM trade_plans tp
                LEFT JOIN pressure_blocks pb ON tp.block_id = pb.id
                WHERE tp.id = %s
                """,
                (plan_id,),
            )
            return await cur.fetchone()

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
                SELECT COUNT(*) AS cnt FROM trade_plans
                WHERE execution_grade IN ('A', 'A+')
                  AND created_at > NOW() - INTERVAL '24 hours'
                """
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

    # ----- market_snapshots -----

    async def insert_market_snapshot(self, snapshot: dict) -> int:
        async with get_cursor() as cur:
            await cur.execute(
                """
                INSERT INTO market_snapshots
                    (block_id, symbol, signal_start_utc, signal_end_utc,
                     price_at_start, price_at_end, spread_points,
                     d1_bias, h4_structure, h1_phase, m15_phase,
                     chart_bias, chart_phase,
                     support_zone, resistance_zone, key_level, raw_ohlc)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
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
                    snapshot.get("d1_bias"),
                    snapshot.get("h4_structure"),
                    snapshot.get("h1_phase"),
                    snapshot.get("m15_phase"),
                    snapshot.get("chart_bias"),
                    snapshot.get("chart_phase"),
                    snapshot.get("support_zone"),
                    snapshot.get("resistance_zone"),
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
                       ms.price_at_end AS price_at_end
                FROM trade_plans tp
                LEFT JOIN signal_outcomes so
                  ON so.trade_plan_id = tp.id
                LEFT JOIN pressure_blocks pb
                  ON pb.id = tp.block_id
                LEFT JOIN LATERAL (
                    SELECT chart_phase, price_at_end
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
                    chart_phase, execution_side, signal_end_utc, price_at_signal,
                    price_after_15m, price_after_30m, price_after_60m,
                    mfe_15m, mae_15m, mfe_30m, mae_30m, mfe_60m, mae_60m,
                    result_label, raw_result, updated_at
                )
                VALUES (
                    %(trade_plan_id)s, %(symbol)s, %(pressure_grade)s, %(execution_grade)s,
                    %(chart_phase)s, %(execution_side)s, %(signal_end_utc)s, %(price_at_signal)s,
                    %(price_after_15m)s, %(price_after_30m)s, %(price_after_60m)s,
                    %(mfe_15m)s, %(mae_15m)s, %(mfe_30m)s, %(mae_30m)s, %(mfe_60m)s, %(mae_60m)s,
                    %(result_label)s, %(raw_result)s::jsonb, NOW()
                )
                ON CONFLICT (trade_plan_id) DO UPDATE SET
                    symbol = EXCLUDED.symbol,
                    pressure_grade = EXCLUDED.pressure_grade,
                    execution_grade = EXCLUDED.execution_grade,
                    chart_phase = EXCLUDED.chart_phase,
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

            return {
                "total": total,
                "strong_pct": round(strong_pct, 2),
                "avg_mfe_30m": float(row.get("avg_mfe_30m") or 0),
                "avg_mae_30m": float(row.get("avg_mae_30m") or 0),
                "best_phase": best_phase,
                "worst_phase": worst_phase,
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


def _json_or_none(obj: Any) -> str | None:
    if obj is None:
        return None
    import json
    return json.dumps(obj, default=str)
