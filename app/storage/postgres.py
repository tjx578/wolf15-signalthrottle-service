from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import psycopg
from psycopg.rows import dict_row

from app.config import settings

logger = logging.getLogger(__name__)

_pool: psycopg.AsyncConnection | None = None


async def get_connection() -> psycopg.AsyncConnection:
    global _pool
    if _pool is None or _pool.closed:
        _pool = await psycopg.AsyncConnection.connect(
            settings.database_url,
            row_factory=dict_row,
            autocommit=False,
        )
    return _pool


@asynccontextmanager
async def get_cursor() -> AsyncIterator[psycopg.AsyncCursor]:
    conn = await get_connection()
    async with conn.cursor(row_factory=dict_row) as cur:
        yield cur
    await conn.commit()


async def init_db() -> None:
    """Run schema.sql to ensure all tables exist."""
    import importlib.resources as pkg_resources
    from pathlib import Path

    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    conn = await get_connection()
    async with conn.cursor() as cur:
        await cur.execute(schema_sql)
    await conn.commit()
    logger.info("Database schema initialized")


async def close_db() -> None:
    global _pool
    if _pool and not _pool.closed:
        await _pool.close()
        _pool = None
