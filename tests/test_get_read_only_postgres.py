from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from app.config import settings
from app.main import create_app


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def _bootstrap_schema(database_url: str) -> None:
    schema_sql = Path("app/storage/schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(schema_sql)


def _schema_checksum(database_url: str, schema_name: str) -> tuple:
    with psycopg.connect(database_url, autocommit=True) as conn:
        table_rows = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (schema_name,),
        ).fetchall()
        checksum: list[tuple[str, int, str]] = []
        for (table_name,) in table_rows:
            query = sql.SQL(
                """
                SELECT
                    COUNT(*)::BIGINT,
                    MD5(COALESCE(STRING_AGG(row_hash, '' ORDER BY row_hash), ''))
                FROM (
                    SELECT MD5(TO_JSONB(t)::TEXT) AS row_hash
                    FROM {}.{} AS t
                ) AS rows
                """
            ).format(sql.Identifier(schema_name), sql.Identifier(table_name))
            count, digest = conn.execute(query).fetchone()
            checksum.append((table_name, count, digest))
    return tuple(checksum)


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="OPTIONAL_EXTERNAL_INTEGRATION: TEST_DATABASE_URL is not configured",
)
def test_owner_get_routes_and_replay_attempt_leave_postgres_state_unchanged(monkeypatch) -> None:
    assert TEST_DATABASE_URL is not None
    _bootstrap_schema(TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)

    paths = (
        "/",
        "/partials/stats",
        "/partials/active_blocks",
        "/partials/radar_signals",
        "/partials/failed_signals",
        "/partials/watchlist_signals",
        "/series-detail/USDJPY",
        "/engine-logs/daily?date=2026-05-01",
        "/partials/engine-logs/daily?date=2026-05-01",
        "/signals/latest",
        "/signals/history",
        "/signals/series",
        "/signals/engine-logs/daily?date=2026-05-01",
        "/blocks/active",
        "/blocks/history",
        "/health/live",
        "/health/ready",
    )
    with TestClient(
        create_app(),
        headers={"Authorization": "Basic b3duZXI6c2VjcmV0"},
    ) as client:
        before = _schema_checksum(TEST_DATABASE_URL, settings.db_schema)
        responses = [client.get(path) for path in paths]
        replay_attempt = client.post(
            "/replay/logs",
            json={"logs": "must not reach legacy replay"},
        )
        after = _schema_checksum(TEST_DATABASE_URL, settings.db_schema)
    assert all(response.status_code == 200 for response in responses), [
        (path, response.status_code, response.text[:200])
        for path, response in zip(paths, responses, strict=True)
        if response.status_code != 200
    ]
    assert replay_attempt.status_code == 404
    assert after == before
