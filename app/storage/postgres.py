from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, cast

import psycopg
from psycopg import sql
from psycopg.rows import DictRow, dict_row

from app.config import settings

logger = logging.getLogger(__name__)

_pool: "psycopg.AsyncConnection[DictRow] | None" = None
_LEGACY_BOOTSTRAP_SENTINEL_TABLE = "pressure_blocks"


async def get_connection() -> "psycopg.AsyncConnection[DictRow]":
    global _pool
    if _pool is None or _pool.closed:
        conn = await psycopg.AsyncConnection.connect(
            settings.database_url,
            row_factory=dict_row,  # type: ignore[arg-type]
            autocommit=False,
        )
        _pool = cast("psycopg.AsyncConnection[DictRow]", conn)
        await _configure_connection(_pool)
    return _pool


async def _configure_connection(conn: "psycopg.AsyncConnection[DictRow]") -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            sql.SQL("SET search_path TO {}, public").format(
                sql.Identifier(settings.db_schema)
            )
        )
    await conn.commit()


@asynccontextmanager
async def get_cursor() -> AsyncIterator["psycopg.AsyncCursor[DictRow]"]:
    conn = await get_connection()
    async with conn.cursor(row_factory=dict_row) as cur:
        try:
            yield cur
        except Exception:
            await conn.rollback()
            raise
    await conn.commit()


async def _table_exists(
    conn: "psycopg.AsyncConnection[DictRow]",
    table_name: str,
) -> bool:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
            ) AS table_exists
            """,
            (settings.db_schema, table_name),
        )
        row = await cur.fetchone()
    return bool(row and row.get("table_exists"))


async def init_db() -> None:
    """Run schema.sql only for fresh databases.

    Existing legacy databases already have the base tables, but may not yet have
    newer columns referenced by indexes inside schema.sql. In that case we skip
    the base bootstrap and let additive migrations bring the schema forward.
    """
    from pathlib import Path

    conn = await get_connection()
    if await _table_exists(conn, _LEGACY_BOOTSTRAP_SENTINEL_TABLE):
        logger.info(
            "Existing %s table detected; skipping base schema bootstrap",
            _LEGACY_BOOTSTRAP_SENTINEL_TABLE,
        )
        return

    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    try:
        async with conn.cursor() as cur:
            await cur.execute(schema_sql)  # type: ignore[arg-type]
        await conn.commit()
        logger.info("Database schema initialized")
    except Exception:
        # Avoid leaving the connection in an aborted-transaction state for
        # subsequent callers (e.g. migrations that follow init_db).
        try:
            await conn.rollback()
        except Exception:
            pass
        raise


async def close_db() -> None:
    global _pool
    if _pool and not _pool.closed:
        await _pool.close()
        _pool = None
