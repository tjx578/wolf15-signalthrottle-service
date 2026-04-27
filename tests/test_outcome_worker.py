from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.outcomes.outcome_worker import OutcomeWorker


class _FakeRepo:
    def __init__(self, plans):
        self.plans = plans
        self.upserts: list[tuple[int, dict]] = []

    async def get_trade_plans_without_outcome(self, limit=20):
        return list(self.plans)

    async def upsert_signal_outcome(self, trade_plan_id, result):
        self.upserts.append((trade_plan_id, result))
        return 1


class _FakeTracker:
    async def evaluate(self, plan):
        return {
            "symbol": plan["symbol"],
            "result_label": "FOLLOW_THROUGH_STRONG",
        }


def test_worker_skips_when_no_finnhub_key(monkeypatch):
    import app.outcomes.outcome_worker as worker_mod

    monkeypatch.setattr(worker_mod.settings, "finnhub_api_key", None)
    repo = _FakeRepo([{"id": 1, "symbol": "EURUSD", "payload": {}}])
    worker = OutcomeWorker(repo=repo)

    stats = asyncio.run(worker.process_due_outcomes())
    assert stats == {"considered": 0, "processed": 0, "skipped": 0, "errors": 0}
    assert repo.upserts == []


def test_worker_processes_due_plan(monkeypatch):
    import app.outcomes.outcome_worker as worker_mod

    monkeypatch.setattr(worker_mod.settings, "finnhub_api_key", "fake-key")

    class _FakeFinnhub:
        def __init__(self, api_key):
            self.api_key = api_key

    monkeypatch.setattr(worker_mod, "FinnhubClient", _FakeFinnhub)
    monkeypatch.setattr(worker_mod, "MFEMAETracker", lambda _client: _FakeTracker())

    old_signal_end = datetime.now(timezone.utc) - timedelta(minutes=120)
    repo = _FakeRepo(
        [
            {
                "id": 42,
                "symbol": "USDJPY",
                "payload": {"signal_end_utc": old_signal_end.isoformat()},
            }
        ]
    )

    worker = OutcomeWorker(repo=repo)
    stats = asyncio.run(worker.process_due_outcomes())

    assert stats["processed"] == 1
    assert repo.upserts and repo.upserts[0][0] == 42
    assert repo.upserts[0][1]["result_label"] == "FOLLOW_THROUGH_STRONG"


def test_worker_skips_not_yet_due(monkeypatch):
    import app.outcomes.outcome_worker as worker_mod

    monkeypatch.setattr(worker_mod.settings, "finnhub_api_key", "fake-key")
    monkeypatch.setattr(worker_mod, "FinnhubClient", lambda api_key: None)
    monkeypatch.setattr(worker_mod, "MFEMAETracker", lambda _client: _FakeTracker())

    recent_end = datetime.now(timezone.utc) - timedelta(minutes=10)
    repo = _FakeRepo(
        [
            {
                "id": 7,
                "symbol": "EURUSD",
                "payload": {"signal_end_utc": recent_end.isoformat()},
            }
        ]
    )
    worker = OutcomeWorker(repo=repo)
    stats = asyncio.run(worker.process_due_outcomes())

    assert stats["skipped"] == 1
    assert stats["processed"] == 0
    assert repo.upserts == []
