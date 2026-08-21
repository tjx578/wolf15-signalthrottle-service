from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

import psycopg
from psycopg import sql
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import settings

logger = logging.getLogger(__name__)

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_pool: "AsyncConnectionPool[psycopg.AsyncConnection[DictRow]] | None" = None
_pool_open_lock = asyncio.Lock()
_LEGACY_BOOTSTRAP_SENTINEL_TABLE = "pressure_blocks"


def _build_pool() -> "AsyncConnectionPool[psycopg.AsyncConnection[DictRow]]":
    return AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
        timeout=settings.database_pool_timeout_seconds,
        reconnect_timeout=settings.database_pool_reconnect_timeout_seconds,
        kwargs={
            "row_factory": dict_row,
            "autocommit": False,
        },
        configure=_configure_connection,
        check=AsyncConnectionPool.check_connection,
        open=False,
        name="observer-postgres-pool",
    )


async def open_db_pool() -> "AsyncConnectionPool[psycopg.AsyncConnection[DictRow]]":
    global _pool
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    async with _pool_open_lock:
        if _pool is None or _pool.closed:
            _pool = _build_pool()
            await _pool.open(wait=True)
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
async def get_connection() -> AsyncIterator["psycopg.AsyncConnection[DictRow]"]:
    pool = await open_db_pool()
    async with pool.connection(
        timeout=settings.database_pool_timeout_seconds,
    ) as conn:
        yield conn


@asynccontextmanager
async def get_cursor() -> AsyncIterator["psycopg.AsyncCursor[DictRow]"]:
    async with get_connection() as conn:
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

    async with get_connection() as conn:
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


def get_pool_stats() -> dict[str, int]:
    if _pool is None:
        return {}
    return _pool.get_stats()


async def close_db() -> None:
    global _pool
    pool = _pool
    _pool = None
    if pool is not None and not pool.closed:
        await pool.close()
