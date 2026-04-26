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
