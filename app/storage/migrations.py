from __future__ import annotations

import logging

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
        await cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = 'signal_events'
                      AND column_name = 'event_hash'
                ) THEN
                    ALTER TABLE signal_events ADD COLUMN event_hash TEXT;
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_events_event_hash
                    ON signal_events(event_hash);
                END IF;
            END $$;
            """,
            (settings.db_schema,),
        )
    logger.info("migration_001: event_hash column ensured")
