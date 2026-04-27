from __future__ import annotations

import logging
from typing import LiteralString, cast

from psycopg import sql

from app.config import settings
from app.storage.postgres import get_cursor

logger = logging.getLogger(__name__)


async def run_migrations() -> list[dict]:
    """Run any pending migrations beyond the base schema.

    Returns a list of per-migration results so callers (e.g. /debug/run-migrations)
    can surface success/failure explicitly instead of relying on log scraping.
    """
    migrations = [
        _migration_001_add_event_hash_if_missing,
        _migration_002_ensure_phase2_columns,
        _migration_003_ensure_realtime_columns,
        _migration_004_ensure_signal_outcomes_columns,
        _migration_005_ensure_pressure_series_table,
        _migration_006_ensure_pressure_blocks_block_hash,
        _migration_007_ensure_block_pending_reason_columns,
    ]
    results: list[dict] = []
    for m in migrations:
        try:
            await m()
            results.append({"name": m.__name__, "status": "ok"})
            logger.info("Migration %s applied", m.__name__)
        except Exception as exc:
            results.append({"name": m.__name__, "status": "error", "error": str(exc)})
            logger.error("Migration %s FAILED: %s", m.__name__, exc, exc_info=True)
    return results


async def _migration_001_add_event_hash_if_missing() -> None:
    async with get_cursor() as cur:
        signal_events = sql.Identifier(settings.db_schema, "signal_events")
        index_name = sql.Identifier("idx_signal_events_event_hash")

        await cur.execute(
            sql.SQL(
                "ALTER TABLE {} ADD COLUMN IF NOT EXISTS event_hash TEXT"
            ).format(signal_events)
        )
        await cur.execute(
            sql.SQL(
                "CREATE UNIQUE INDEX IF NOT EXISTS {} ON {} (event_hash)"
            ).format(index_name, signal_events)
        )
    logger.info("migration_001: event_hash column ensured")


async def _ensure_column(table_name: str, column_name: str, type_sql: str) -> None:
    async with get_cursor() as cur:
        await cur.execute(
            sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} {}")
            .format(
                sql.Identifier(settings.db_schema, table_name),
                sql.Identifier(column_name),
                # type_sql is sourced exclusively from hard-coded literals in
                # this module (never user input); cast to LiteralString to
                # satisfy psycopg's SQL-injection-safe type signature.
                sql.SQL(cast(LiteralString, type_sql)),
            )
        )


async def _ensure_index(index_name: str, table_name: str, columns_sql: str) -> None:
    async with get_cursor() as cur:
        await cur.execute(
            sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} ({})").format(
                sql.Identifier(index_name),
                sql.Identifier(settings.db_schema, table_name),
                sql.SQL(cast(LiteralString, columns_sql)),
            )
        )


async def _migration_002_ensure_phase2_columns() -> None:
    pressure_block_columns = [
        ("pressure_status", "TEXT"),
        ("block_relation", "TEXT"),
        ("previous_block_id", "BIGINT"),
        ("finalize_mode", "TEXT"),
        ("is_active", "BOOLEAN DEFAULT FALSE"),
    ]
    market_snapshot_columns = [
        ("signal_start_utc", "TIMESTAMPTZ"),
        ("signal_end_utc", "TIMESTAMPTZ"),
        ("price_at_start", "NUMERIC"),
        ("price_at_end", "NUMERIC"),
        ("spread_points", "NUMERIC"),
        ("d1_bias", "TEXT"),
        ("h4_structure", "TEXT"),
        ("h1_phase", "TEXT"),
        ("m15_phase", "TEXT"),
        ("chart_bias", "TEXT"),
        ("chart_phase", "TEXT"),
        ("support_zone", "TEXT"),
        ("resistance_zone", "TEXT"),
        ("key_level", "TEXT"),
        ("raw_ohlc", "JSONB"),
    ]
    trade_plan_columns = [
        ("execution_side", "TEXT"),
        ("chart_phase", "TEXT"),
        ("entry_zone", "TEXT"),
        ("breakout_level", "TEXT"),
        ("reclaim_level", "TEXT"),
        ("invalidation", "TEXT"),
        ("tp1", "TEXT"),
        ("tp2", "TEXT"),
        ("tp3", "TEXT"),
        ("message", "TEXT"),
        ("payload", "JSONB NOT NULL DEFAULT '{}'::jsonb"),
        ("pressure_status", "TEXT"),
        ("signal_bucket", "TEXT"),
    ]

    for column_name, type_sql in pressure_block_columns:
        await _ensure_column("pressure_blocks", column_name, type_sql)

    for column_name, type_sql in market_snapshot_columns:
        await _ensure_column("market_snapshots", column_name, type_sql)

    for column_name, type_sql in trade_plan_columns:
        await _ensure_column("trade_plans", column_name, type_sql)

    await _ensure_index(
        "idx_st_market_snapshots_symbol_time",
        "market_snapshots",
        "symbol, created_at DESC",
    )
    await _ensure_index(
        "idx_st_trade_plans_symbol_time",
        "trade_plans",
        "symbol, created_at DESC",
    )
    await _ensure_index(
        "idx_st_trade_plans_grade_time",
        "trade_plans",
        "execution_grade, created_at DESC",
    )
    logger.info("migration_002: phase 2 columns ensured")


async def _migration_003_ensure_realtime_columns() -> None:
    await _ensure_column("pressure_blocks", "last_event_utc", "TIMESTAMPTZ")
    await _ensure_column(
        "pressure_blocks",
        "updated_at",
        "TIMESTAMPTZ DEFAULT NOW()",
    )
    await _ensure_index(
        "idx_st_pressure_blocks_active",
        "pressure_blocks",
        "is_active, end_utc DESC",
    )
    logger.info("migration_003: realtime columns ensured")


async def _ensure_unique_index(index_name: str, table_name: str, columns_sql: str) -> None:
    async with get_cursor() as cur:
        await cur.execute(
            sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {} ON {} ({})").format(
                sql.Identifier(index_name),
                sql.Identifier(settings.db_schema, table_name),
                sql.SQL(cast(LiteralString, columns_sql)),
            )
        )


async def _migration_004_ensure_signal_outcomes_columns() -> None:
    # Create base table if missing (defensive — schema.sql may not have run)
    async with get_cursor() as cur:
        await cur.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {} (
                    id BIGSERIAL PRIMARY KEY,
                    trade_plan_id BIGINT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            ).format(sql.Identifier(settings.db_schema, "signal_outcomes"))
        )

    columns = [
        ("symbol", "TEXT"),
        ("pressure_grade", "TEXT"),
        ("execution_grade", "TEXT"),
        ("chart_phase", "TEXT"),
        ("execution_side", "TEXT"),
        ("signal_end_utc", "TIMESTAMPTZ"),
        ("price_at_signal", "NUMERIC"),
        ("price_after_15m", "NUMERIC"),
        ("price_after_30m", "NUMERIC"),
        ("price_after_60m", "NUMERIC"),
        ("mfe_15m", "NUMERIC"),
        ("mae_15m", "NUMERIC"),
        ("mfe_30m", "NUMERIC"),
        ("mae_30m", "NUMERIC"),
        ("mfe_60m", "NUMERIC"),
        ("mae_60m", "NUMERIC"),
        ("result_label", "TEXT"),
        ("raw_result", "JSONB"),
        ("updated_at", "TIMESTAMPTZ DEFAULT NOW()"),
    ]

    for column_name, type_sql in columns:
        await _ensure_column("signal_outcomes", column_name, type_sql)

    await _ensure_unique_index(
        "idx_st_signal_outcomes_trade_plan_id",
        "signal_outcomes",
        "trade_plan_id",
    )
    await _ensure_index(
        "idx_st_signal_outcomes_symbol_time",
        "signal_outcomes",
        "symbol, signal_end_utc DESC",
    )
    await _ensure_index(
        "idx_st_signal_outcomes_phase_grade",
        "signal_outcomes",
        "chart_phase, pressure_grade, execution_grade",
    )
    logger.info("migration_004: signal_outcomes columns ensured")


async def _migration_005_ensure_pressure_series_table() -> None:
    async with get_cursor() as cur:
        await cur.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {} (
                    id BIGSERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    start_utc TIMESTAMPTZ NOT NULL,
                    end_utc TIMESTAMPTZ NOT NULL,
                    duration_minutes NUMERIC NOT NULL,
                    event_count INT NOT NULL,
                    density_per_minute NUMERIC NOT NULL,
                    max_gap_seconds NUMERIC,
                    block_count INT NOT NULL DEFAULT 1,
                    block_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                    latest_block_id BIGINT,
                    latest_trade_plan_id BIGINT,
                    latest_pressure_grade TEXT,
                    best_pressure_grade TEXT,
                    pressure_status TEXT,
                    finalize_mode TEXT,
                    is_active BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            ).format(sql.Identifier(settings.db_schema, "pressure_series"))
        )

    columns = [
        ("symbol", "TEXT"),
        ("start_utc", "TIMESTAMPTZ"),
        ("end_utc", "TIMESTAMPTZ"),
        ("duration_minutes", "NUMERIC"),
        ("event_count", "INT"),
        ("density_per_minute", "NUMERIC"),
        ("max_gap_seconds", "NUMERIC"),
        ("block_count", "INT NOT NULL DEFAULT 1"),
        ("block_ids", "JSONB NOT NULL DEFAULT '[]'::jsonb"),
        ("latest_block_id", "BIGINT"),
        ("latest_trade_plan_id", "BIGINT"),
        ("latest_pressure_grade", "TEXT"),
        ("best_pressure_grade", "TEXT"),
        ("pressure_status", "TEXT"),
        ("finalize_mode", "TEXT"),
        ("is_active", "BOOLEAN DEFAULT FALSE"),
        ("updated_at", "TIMESTAMPTZ DEFAULT NOW()"),
        ("created_at", "TIMESTAMPTZ DEFAULT NOW()"),
    ]
    for column_name, type_sql in columns:
        await _ensure_column("pressure_series", column_name, type_sql)

    await _ensure_unique_index(
        "idx_st_pressure_series_symbol_window",
        "pressure_series",
        "symbol, start_utc, end_utc",
    )
    await _ensure_index(
        "idx_st_pressure_series_symbol_time",
        "pressure_series",
        "symbol, end_utc DESC",
    )
    await _ensure_index(
        "idx_st_pressure_series_latest_block",
        "pressure_series",
        "latest_block_id",
    )
    logger.info("migration_005: pressure_series table ensured")


async def _migration_006_ensure_pressure_blocks_block_hash() -> None:
    """Add canonical block_hash column + partial unique index for idempotent
    block writes during replay."""
    await _ensure_column("pressure_blocks", "block_hash", "TEXT")
    # Partial unique index: only enforce uniqueness on non-NULL hashes so that
    # legacy rows without a hash do not block the migration.
    async with get_cursor() as cur:
        await cur.execute(
            sql.SQL(
                "CREATE UNIQUE INDEX IF NOT EXISTS {} ON {} (block_hash) "
                "WHERE block_hash IS NOT NULL"
            ).format(
                sql.Identifier("uq_st_pressure_blocks_block_hash"),
                sql.Identifier(settings.db_schema, "pressure_blocks"),
            )
        )
    logger.info("migration_006: pressure_blocks.block_hash ensured")


async def _migration_007_ensure_block_pending_reason_columns() -> None:
    """Add status/reason columns so B+ blocks whose enrichment fails do not
    silently disappear from the dashboard. Default values keep legacy rows
    backward-compatible."""
    columns = [
        ("market_context_status", "TEXT DEFAULT 'NOT_REQUESTED'"),
        ("trade_plan_status", "TEXT DEFAULT 'NOT_REQUIRED'"),
        ("pending_reason", "TEXT"),
    ]
    for column_name, type_sql in columns:
        await _ensure_column("pressure_blocks", column_name, type_sql)
    logger.info("migration_007: pressure_blocks pending-reason columns ensured")
