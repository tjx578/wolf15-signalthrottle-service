from __future__ import annotations

import asyncio

import app.storage.postgres as postgres


class FakeCursor:
    def __init__(self, responses: list[dict], executed: list[str]) -> None:
        self._responses = responses
        self._executed = executed
        self._last_response: dict | None = None

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, query, params=None) -> None:
        self._executed.append(str(query).strip())
        if "information_schema.tables" in str(query):
            self._last_response = self._responses.pop(0)
        else:
            self._last_response = None

    async def fetchone(self) -> dict | None:
        return self._last_response


class FakeConnection:
    def __init__(self, responses: list[dict], executed: list[str]) -> None:
        self._responses = responses
        self._executed = executed
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self, row_factory=None) -> FakeCursor:
        return FakeCursor(self._responses, self._executed)

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


def test_init_db_skips_schema_sql_for_legacy_database(monkeypatch) -> None:
    executed: list[str] = []
    conn = FakeConnection([{"table_exists": True}], executed)

    async def _get_connection() -> FakeConnection:
        return conn

    monkeypatch.setattr(postgres, "get_connection", _get_connection)
    monkeypatch.setattr("pathlib.Path.read_text", lambda self, encoding="utf-8": "SELECT 1;")

    asyncio.run(postgres.init_db())

    assert any("information_schema.tables" in query for query in executed)
    assert all("SELECT 1;" not in query for query in executed)
    assert conn.commit_calls == 0


def test_init_db_runs_schema_sql_for_fresh_database(monkeypatch) -> None:
    executed: list[str] = []
    conn = FakeConnection([{"table_exists": False}], executed)

    async def _get_connection() -> FakeConnection:
        return conn

    monkeypatch.setattr(postgres, "get_connection", _get_connection)
    monkeypatch.setattr("pathlib.Path.read_text", lambda self, encoding="utf-8": "SELECT 1;")

    asyncio.run(postgres.init_db())

    assert any("information_schema.tables" in query for query in executed)
    assert any("SELECT 1;" in query for query in executed)
    assert conn.commit_calls == 1