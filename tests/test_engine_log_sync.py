from __future__ import annotations

from datetime import datetime, timezone

import app.ingestion.engine_log_sync as engine_log_sync


class FakeSignalRepository:
    duplicate_timestamps: set[datetime] = set()

    def __init__(self) -> None:
        self.inserted: list[datetime] = []
        self.upserted: list[str] = []

    async def insert_signal_event(self, **kwargs) -> dict:
        timestamp_utc = kwargs["timestamp_utc"]
        if timestamp_utc in self.__class__.duplicate_timestamps:
            return {"id": 1, "duplicate": True}

        self.inserted.append(timestamp_utc)
        return {"id": len(self.inserted), "duplicate": False}

    async def upsert_live_block_from_event(self, event, *, max_event_gap_seconds: int, chart_offset_hours: int) -> dict:
        self.upserted.append(event.symbol)
        return {"id": len(self.upserted), "action": "updated"}


def test_owner_day_window_utc_uses_owner_timezone() -> None:
    now_utc = datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)

    start_utc, end_utc = engine_log_sync.owner_day_window_utc(now_utc, "Asia/Makassar")

    assert start_utc == datetime(2026, 4, 26, 16, 0, tzinfo=timezone.utc)
    assert end_utc == now_utc


async def _fake_fetch_logs(self, start_utc: datetime, end_utc: datetime) -> str:
    return "\n".join(
        [
            "2026-04-27T07:20:36Z [SignalThrottle] GBPUSD THROTTLED — 3 signals in last 300s (max 3)",
            "2026-04-27T07:21:00Z [SignalThrottle] GBPUSD THROTTLED — 3 signals in last 300s (max 3)",
            "2026-04-27T07:21:10Z unrelated log line",
        ]
    )


def test_sync_today_ingests_new_engine_logs(monkeypatch) -> None:
    repository = FakeSignalRepository()

    monkeypatch.setattr(engine_log_sync.settings, "engine_log_sync_enabled", True)
    monkeypatch.setattr(engine_log_sync.settings, "engine_log_source_url", "https://example.com/logs")
    monkeypatch.setattr(engine_log_sync.EngineLogSync, "fetch_logs", _fake_fetch_logs)

    syncer = engine_log_sync.EngineLogSync(
        repo_factory=lambda: repository,
        now_provider=lambda: datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc),
    )

    result = engine_log_sync.asyncio.run(syncer.sync_today())

    assert result["status"] == "ok"
    assert result["events_parsed"] == 2
    assert result["events_stored"] == 2
    assert result["duplicates_skipped"] == 0
    assert repository.upserted == ["GBPUSD", "GBPUSD"]


def test_sync_today_skips_duplicate_engine_logs(monkeypatch) -> None:
    duplicate_timestamp = datetime(2026, 4, 27, 7, 20, 36, tzinfo=timezone.utc)
    FakeSignalRepository.duplicate_timestamps = {duplicate_timestamp}
    repository = FakeSignalRepository()

    monkeypatch.setattr(engine_log_sync.settings, "engine_log_sync_enabled", True)
    monkeypatch.setattr(engine_log_sync.settings, "engine_log_source_url", "https://example.com/logs")
    monkeypatch.setattr(engine_log_sync.EngineLogSync, "fetch_logs", _fake_fetch_logs)

    syncer = engine_log_sync.EngineLogSync(
        repo_factory=lambda: repository,
        now_provider=lambda: datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc),
    )

    result = engine_log_sync.asyncio.run(syncer.sync_today())

    assert result["events_parsed"] == 2
    assert result["events_stored"] == 1
    assert result["duplicates_skipped"] == 1
    assert repository.upserted == ["GBPUSD"]
    FakeSignalRepository.duplicate_timestamps = set()