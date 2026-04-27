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


async def init_db() -> None:
    """Run schema.sql to ensure all tables exist."""
    from pathlib import Path

    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    conn = await get_connection()
    async with conn.cursor() as cur:
        await cur.execute(schema_sql)  # type: ignore[arg-type]
    await conn.commit()
    logger.info("Database schema initialized")


async def close_db() -> None:
    global _pool
    if _pool and not _pool.closed:
        await _pool.close()
        _pool = None
