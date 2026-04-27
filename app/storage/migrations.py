from __future__ import annotations

import logging

from psycopg import sql

from app.config import settings
from app.storage.postgres import get_cursor

logger = logging.getLogger(__name__)


async def run_migrations() -> None:
    """Run any pending migrations beyond the base schema."""
    migrations = [
        _migration_001_add_event_hash_if_missing,
        _migration_002_ensure_phase2_columns,
        _migration_003_ensure_realtime_columns,
    ]
    for m in migrations:
        try:
            await m()
        except Exception as exc:
            logger.warning("Migration %s skipped: %s", m.__name__, exc)


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
                sql.SQL(type_sql),
            )
        )


async def _ensure_index(index_name: str, table_name: str, columns_sql: str) -> None:
    async with get_cursor() as cur:
        await cur.execute(
            sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} ({})").format(
                sql.Identifier(index_name),
                sql.Identifier(settings.db_schema, table_name),
                sql.SQL(columns_sql),
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
