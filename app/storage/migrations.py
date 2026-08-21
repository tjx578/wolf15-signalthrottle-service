from __future__ import annotations

import logging
from typing import LiteralString, cast

from psycopg import sql

from app.config import settings
from app.storage.observer_schema import (
    OBSERVER_DURABLE_FOUNDATION_DOWN_SQL,
    OBSERVER_DURABLE_FOUNDATION_REVISION,
    OBSERVER_DURABLE_FOUNDATION_UP_SQL,
    OBSERVER_DURABLE_TABLES,
    OBSERVER_SCHEMA,
)
from app.storage.postgres import get_cursor

logger = logging.getLogger(__name__)

_PRESSURE_BLOCKS_REQUIRED_COLUMNS = (
    "block_hash",
    "market_context_status",
    "trade_plan_status",
    "pending_reason",
    "block_mode",
    "pressure_temperature",
    "wave_count",
    "interrupted_by",
    "theme_cluster",
)
_PRESSURE_BLOCKS_REQUIRED_INDEXES = (
    "uq_st_pressure_blocks_block_hash",
)


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
        _migration_008_ensure_trade_plans_reason_code,
        _migration_009_backfill_signal_outcomes_h4_context_type,
        _migration_010_cleanup_duplicate_replay_pressure_blocks,
        _migration_011_cleanup_overlapping_replay_pressure_blocks,
        _migration_012_ensure_pressure_series_reason_columns,
        _migration_013_ensure_phase1_raw_logs_and_block_fields,
        _migration_014_observer_durable_foundation,
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


async def get_pressure_blocks_schema_status() -> dict:
    table_exists = False
    existing_columns: set[str] = set()
    existing_indexes: set[str] = set()

    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = 'pressure_blocks'
            ) AS table_exists
            """,
            (settings.db_schema,),
        )
        row = await cur.fetchone()
        table_exists = bool(row and row.get("table_exists"))

        if table_exists:
            await cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'pressure_blocks'
                """,
                (settings.db_schema,),
            )
            existing_columns = {r["column_name"] for r in await cur.fetchall()}

            await cur.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = %s AND tablename = 'pressure_blocks'
                """,
                (settings.db_schema,),
            )
            existing_indexes = {r["indexname"] for r in await cur.fetchall()}

    missing_columns = [
        column for column in _PRESSURE_BLOCKS_REQUIRED_COLUMNS if column not in existing_columns
    ]
    missing_indexes = [
        index_name
        for index_name in _PRESSURE_BLOCKS_REQUIRED_INDEXES
        if index_name not in existing_indexes
    ]

    pressure_blocks_status = {
        column: column in existing_columns for column in _PRESSURE_BLOCKS_REQUIRED_COLUMNS
    }
    pressure_blocks_status.update(
        {index_name: index_name in existing_indexes for index_name in _PRESSURE_BLOCKS_REQUIRED_INDEXES}
    )

    return {
        "pressure_blocks": pressure_blocks_status,
        "table_exists": table_exists,
        "missing_columns": missing_columns,
        "missing_indexes": missing_indexes,
        "status": (
            "ok"
            if table_exists and not missing_columns and not missing_indexes
            else "DATABASE_SCHEMA_OUT_OF_SYNC"
        ),
    }


async def get_observer_schema_status() -> dict:
    async with get_cursor() as cur:
        await cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            """,
            (OBSERVER_SCHEMA,),
        )
        tables = {row["table_name"] for row in await cur.fetchall()}
        if "schema_revisions" in tables:
            await cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM observer_plane.schema_revisions
                    WHERE revision_id = %s
                ) AS revision_current
                """,
                (OBSERVER_DURABLE_FOUNDATION_REVISION,),
            )
            row = await cur.fetchone()
            revision_current = bool(row and row.get("revision_current"))
        else:
            revision_current = False

    missing_tables = sorted(OBSERVER_DURABLE_TABLES - tables)
    return {
        "schema": OBSERVER_SCHEMA,
        "expected_revision": OBSERVER_DURABLE_FOUNDATION_REVISION,
        "revision_current": revision_current,
        "missing_tables": missing_tables,
        "status": (
            "ok" if revision_current and not missing_tables else "OBSERVER_SCHEMA_OUT_OF_SYNC"
        ),
    }


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
        ("range_low", "NUMERIC"),
        ("range_high", "NUMERIC"),
        ("pivot_mid", "NUMERIC"),
        ("reclaim_level", "NUMERIC"),
        ("breakdown_level", "NUMERIC"),
        ("breakout_level", "NUMERIC"),
        ("d1_bias", "TEXT"),
        ("h4_structure", "TEXT"),
        ("h4_context_type", "TEXT"),
        ("h1_phase", "TEXT"),
        ("m15_phase", "TEXT"),
        ("chart_bias", "TEXT"),
        ("chart_phase", "TEXT"),
        ("support_zone", "TEXT"),
        ("resistance_zone", "TEXT"),
        ("nearest_supply_zone", "TEXT"),
        ("nearest_demand_zone", "TEXT"),
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
        ("h4_context_type", "TEXT"),
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
    await _ensure_index(
        "idx_st_signal_outcomes_h4_context",
        "signal_outcomes",
        "h4_context_type, result_label",
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


async def _migration_008_ensure_trade_plans_reason_code() -> None:
    await _ensure_column("trade_plans", "reason_code", "TEXT")
    logger.info("migration_008: trade_plans.reason_code ensured")


async def _migration_009_backfill_signal_outcomes_h4_context_type() -> None:
    await _ensure_column("signal_outcomes", "h4_context_type", "TEXT")

    async with get_cursor() as cur:
        await cur.execute(
            sql.SQL(
                """
                WITH latest_snapshot AS (
                    SELECT DISTINCT ON (block_id)
                           block_id,
                           h4_context_type
                    FROM {}
                    WHERE h4_context_type IS NOT NULL
                    ORDER BY block_id, created_at DESC
                )
                UPDATE {} so
                SET h4_context_type = COALESCE(
                    latest_snapshot.h4_context_type,
                    tp.payload -> 'snapshot' ->> 'h4_context_type'
                ),
                updated_at = NOW()
                FROM {} tp
                LEFT JOIN latest_snapshot ON latest_snapshot.block_id = tp.block_id
                WHERE so.trade_plan_id = tp.id
                  AND so.h4_context_type IS NULL
                  AND COALESCE(
                        latest_snapshot.h4_context_type,
                        tp.payload -> 'snapshot' ->> 'h4_context_type'
                  ) IS NOT NULL
                """
            ).format(
                sql.Identifier(settings.db_schema, "market_snapshots"),
                sql.Identifier(settings.db_schema, "signal_outcomes"),
                sql.Identifier(settings.db_schema, "trade_plans"),
            )
        )

    logger.info("migration_009: signal_outcomes.h4_context_type backfilled from latest snapshots/trade plan payload")


async def _migration_010_cleanup_duplicate_replay_pressure_blocks() -> None:
    """Remove only exact replay duplicates that have no dependent snapshot or
    trade-plan rows. Keep one canonical representative per identical replay
    identity and preserve any row that already owns downstream artifacts.
    """
    async with get_cursor() as cur:
        await cur.execute(
            sql.SQL(
                """
                WITH ranked AS (
                    SELECT
                        pb.id,
                        ROW_NUMBER() OVER (
                            PARTITION BY COALESCE(
                                pb.block_hash,
                                pb.symbol || '|' || pb.start_utc::text || '|' || pb.end_utc::text || '|' ||
                                COALESCE(pb.event_count::text, '') || '|' || COALESCE(pb.duration_minutes::text, '') || '|' ||
                                COALESCE(pb.pressure_grade, '') || '|' || COALESCE(pb.pressure_status, '')
                            )
                            ORDER BY
                                CASE WHEN tp.id IS NOT NULL THEN 1 ELSE 0 END DESC,
                                CASE WHEN ms.id IS NOT NULL THEN 1 ELSE 0 END DESC,
                                pb.id ASC
                        ) AS rn,
                        tp.id AS trade_plan_id,
                        ms.id AS market_snapshot_id
                    FROM {} pb
                    LEFT JOIN {} tp ON tp.block_id = pb.id
                    LEFT JOIN {} ms ON ms.block_id = pb.id
                    WHERE pb.pressure_status = 'REPLAY'
                )
                DELETE FROM {} pb
                USING ranked
                WHERE pb.id = ranked.id
                  AND ranked.rn > 1
                  AND ranked.trade_plan_id IS NULL
                  AND ranked.market_snapshot_id IS NULL
                """
            ).format(
                sql.Identifier(settings.db_schema, "pressure_blocks"),
                sql.Identifier(settings.db_schema, "trade_plans"),
                sql.Identifier(settings.db_schema, "market_snapshots"),
                sql.Identifier(settings.db_schema, "pressure_blocks"),
            )
        )

    logger.info("migration_010: exact duplicate replay pressure_blocks cleaned up conservatively")


async def _migration_011_cleanup_overlapping_replay_pressure_blocks() -> None:
    """Remove replay-only rows that are near-identical overlapping reconstructions
    of another replay row for the same symbol and have no dependent artifacts.

    This targets the common replay pattern where one alternative reconstruction is
    almost fully covered by another window but differs by a few seconds at the
    boundaries. Keep any row that already owns a trade plan or market snapshot.
    """
    async with get_cursor() as cur:
        await cur.execute(
            sql.SQL(
                """
                WITH candidates AS (
                    SELECT
                        loser.id
                    FROM {pressure_blocks} loser
                    JOIN {pressure_blocks} winner
                      ON winner.symbol = loser.symbol
                     AND winner.id <> loser.id
                     AND winner.pressure_status = 'REPLAY'
                     AND loser.pressure_status = 'REPLAY'
                     AND LEAST(winner.end_utc, loser.end_utc) > GREATEST(winner.start_utc, loser.start_utc)
                    LEFT JOIN {trade_plans} loser_tp ON loser_tp.block_id = loser.id
                    LEFT JOIN {market_snapshots} loser_ms ON loser_ms.block_id = loser.id
                    WHERE loser_tp.id IS NULL
                      AND loser_ms.id IS NULL
                      AND (
                            EXTRACT(EPOCH FROM LEAST(winner.end_utc, loser.end_utc) - GREATEST(winner.start_utc, loser.start_utc))
                            /
                            NULLIF(
                                LEAST(
                                    EXTRACT(EPOCH FROM winner.end_utc - winner.start_utc),
                                    EXTRACT(EPOCH FROM loser.end_utc - loser.start_utc)
                                ),
                                0
                            )
                          ) >= 0.9
                      AND (
                            CASE WHEN winner.start_utc IS NOT NULL AND winner.end_utc IS NOT NULL
                                THEN EXTRACT(EPOCH FROM winner.end_utc - winner.start_utc)
                                ELSE 0 END,
                            COALESCE(winner.event_count, 0),
                            CASE COALESCE(winner.pressure_grade, '')
                                WHEN 'A+' THEN 5
                                WHEN 'A' THEN 4
                                WHEN 'A-' THEN 3
                                WHEN 'B+' THEN 2
                                WHEN 'C' THEN 1
                                ELSE 0
                            END,
                            winner.end_utc,
                            winner.id
                          )
                          >
                          (
                            CASE WHEN loser.start_utc IS NOT NULL AND loser.end_utc IS NOT NULL
                                THEN EXTRACT(EPOCH FROM loser.end_utc - loser.start_utc)
                                ELSE 0 END,
                            COALESCE(loser.event_count, 0),
                            CASE COALESCE(loser.pressure_grade, '')
                                WHEN 'A+' THEN 5
                                WHEN 'A' THEN 4
                                WHEN 'A-' THEN 3
                                WHEN 'B+' THEN 2
                                WHEN 'C' THEN 1
                                ELSE 0
                            END,
                            loser.end_utc,
                            loser.id
                          )
                )
                DELETE FROM {pressure_blocks} pb
                USING candidates
                WHERE pb.id = candidates.id
                """
            ).format(
                pressure_blocks=sql.Identifier(settings.db_schema, "pressure_blocks"),
                trade_plans=sql.Identifier(settings.db_schema, "trade_plans"),
                market_snapshots=sql.Identifier(settings.db_schema, "market_snapshots"),
            )
        )

    logger.info("migration_011: overlapping replay pressure_blocks cleaned up conservatively")


async def _migration_012_ensure_pressure_series_reason_columns() -> None:
    await _ensure_column("pressure_series", "best_valid_block_grade", "TEXT")
    await _ensure_column("pressure_series", "series_reason", "TEXT")
    logger.info("migration_012: pressure_series reason columns ensured")


async def _migration_013_ensure_phase1_raw_logs_and_block_fields() -> None:
    async with get_cursor() as cur:
        await cur.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {} (
                    id BIGSERIAL PRIMARY KEY,
                    timestamp_utc TIMESTAMPTZ,
                    message TEXT NOT NULL,
                    severity TEXT,
                    attributes JSONB,
                    tags JSONB,
                    source_service TEXT DEFAULT 'wolf15-engine',
                    source_path TEXT DEFAULT 'engine_log_sync',
                    log_hash TEXT,
                    is_signalthrottle BOOLEAN DEFAULT FALSE,
                    parse_status TEXT,
                    symbol TEXT,
                    signal_count INT,
                    window_seconds INT,
                    max_signals INT,
                    raw_payload JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            ).format(sql.Identifier(settings.db_schema, "engine_log_entries"))
        )

    raw_log_columns = [
        ("timestamp_utc", "TIMESTAMPTZ"),
        ("message", "TEXT"),
        ("severity", "TEXT"),
        ("attributes", "JSONB"),
        ("tags", "JSONB"),
        ("source_service", "TEXT DEFAULT 'wolf15-engine'"),
        ("source_path", "TEXT DEFAULT 'engine_log_sync'"),
        ("log_hash", "TEXT"),
        ("is_signalthrottle", "BOOLEAN DEFAULT FALSE"),
        ("parse_status", "TEXT"),
        ("symbol", "TEXT"),
        ("signal_count", "INT"),
        ("window_seconds", "INT"),
        ("max_signals", "INT"),
        ("raw_payload", "JSONB"),
        ("created_at", "TIMESTAMPTZ DEFAULT NOW()"),
    ]
    for column_name, type_sql in raw_log_columns:
        await _ensure_column("engine_log_entries", column_name, type_sql)

    await _ensure_unique_index(
        "idx_engine_log_entries_log_hash",
        "engine_log_entries",
        "log_hash",
    )
    await _ensure_index(
        "idx_engine_log_entries_time",
        "engine_log_entries",
        "timestamp_utc DESC",
    )
    await _ensure_index(
        "idx_engine_log_entries_signal_time",
        "engine_log_entries",
        "is_signalthrottle, timestamp_utc DESC",
    )

    block_columns = [
        ("block_mode", "TEXT DEFAULT 'SAME_PAIR_SEQUENCE'"),
        ("pressure_temperature", "TEXT"),
        ("wave_count", "INT DEFAULT 1"),
        ("interrupted_by", "TEXT"),
        ("theme_cluster", "TEXT"),
    ]
    for column_name, type_sql in block_columns:
        await _ensure_column("pressure_blocks", column_name, type_sql)

    logger.info("migration_013: phase1 raw logs and block metadata ensured")


async def _migration_014_observer_durable_foundation() -> None:
    """Create the isolated, revisioned observer-owned durable schema."""
    async with get_cursor() as cur:
        await cur.execute(OBSERVER_DURABLE_FOUNDATION_UP_SQL)
    logger.info(
        "migration_014: observer durable foundation revision %s ensured",
        OBSERVER_DURABLE_FOUNDATION_REVISION,
    )


async def downgrade_observer_durable_foundation() -> None:
    """Rollback hook for disposable-database verification only."""
    async with get_cursor() as cur:
        await cur.execute(OBSERVER_DURABLE_FOUNDATION_DOWN_SQL)
    logger.info(
        "observer durable foundation revision %s removed",
        OBSERVER_DURABLE_FOUNDATION_REVISION,
    )
