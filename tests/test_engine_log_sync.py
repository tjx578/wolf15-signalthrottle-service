from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import asyncio
import pytest
import app.ingestion.engine_log_sync as engine_log_sync
from app.parser.signalthrottle_parser import parse_signalthrottle


class FakeSignalRepository:
    duplicate_timestamps: set[datetime] = set()

    def __init__(self) -> None:
        self.inserted: list[datetime] = []
        self.upserted: list[str] = []
        self.raw_logs: list[str] = []

    async def insert_engine_log_entry(self, **kwargs) -> dict:
        self.raw_logs.append(kwargs["message"])
        return {"id": len(self.raw_logs), "duplicate": False}

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


def test_utc_day_window_uses_midnight_utc() -> None:
    now_utc = datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)

    start_utc, end_utc = engine_log_sync.utc_day_window_utc(now_utc)

    assert start_utc == datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc)
    assert end_utc == now_utc


async def _fake_fetch_logs(self, start_utc: datetime, end_utc: datetime) -> str:
    return "\n".join(
        [
            "2026-04-27T07:20:36Z [SignalThrottle] GBPUSD THROTTLED — 3 signals in last 300s (max 3)",
            "2026-04-27T07:21:00Z [SignalThrottle] GBPUSD THROTTLED — 3 signals in last 300s (max 3)",
            "2026-04-27T07:21:10Z unrelated log line",
        ]
    )


async def _fake_fetch_json_logs(self, start_utc: datetime, end_utc: datetime) -> str:
    return "\n".join(
        [
            '{"message":"[SignalThrottle] GBPUSD THROTTLED — 3 signals in last 300s (max 3)","severity":"error","attributes":{"level":"error"},"timestamp":"2026-04-27T07:15:23.169918856Z"}',
            '{"message":"[SignalThrottle] GBPUSD THROTTLED — 3 signals in last 300s (max 3)","severity":"error","attributes":{"level":"error"},"timestamp":"2026-04-27T07:15:27.593071262Z"}',
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

    result = asyncio.run(syncer.sync_today())

    assert result["status"] == "ok"
    assert result["events_parsed"] == 2
    assert result["events_stored"] == 2
    assert result["duplicates_skipped"] == 0
    assert result["raw_logs_seen"] == 3
    assert result["raw_logs_stored"] == 3
    assert result["non_signalthrottle_logs"] == 1
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

    result = asyncio.run(syncer.sync_today())

    assert result["events_parsed"] == 2
    assert result["events_stored"] == 1
    assert result["duplicates_skipped"] == 1
    assert result["raw_logs_seen"] == 3
    assert repository.upserted == ["GBPUSD"]
    FakeSignalRepository.duplicate_timestamps = set()


def test_sync_today_ingests_json_structured_engine_logs(monkeypatch) -> None:
    repository = FakeSignalRepository()

    monkeypatch.setattr(engine_log_sync.settings, "engine_log_sync_enabled", True)
    monkeypatch.setattr(engine_log_sync.settings, "engine_log_source_url", "https://example.com/logs")
    monkeypatch.setattr(engine_log_sync.EngineLogSync, "fetch_logs", _fake_fetch_json_logs)

    syncer = engine_log_sync.EngineLogSync(
        repo_factory=lambda: repository,
        now_provider=lambda: datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc),
    )

    result = asyncio.run(syncer.sync_today())

    assert result["status"] == "ok"
    assert result["events_parsed"] == 2
    assert result["events_stored"] == 2
    assert result["raw_logs_seen"] == 2
    assert repository.upserted == ["GBPUSD", "GBPUSD"]


def test_parse_engine_log_entries_accepts_railway_csv() -> None:
    csv_logs = "\n".join(
        [
            "message,severity,attributes,tags,timestamp",
            '"[SignalThrottle] EURAUD THROTTLED — 3 signals in last 300s (max 3)",error,"{""level"":""error""}","[""railway""]",2026-05-01T09:12:00.123456789Z',
            '"engine heartbeat",info,"{}","[]",2026-05-01T09:12:03Z',
        ]
    )

    entries = engine_log_sync.parse_engine_log_entries(csv_logs)

    assert len(entries) == 2
    assert entries[0].message.startswith("[SignalThrottle] EURAUD")
    assert entries[0].timestamp_utc == datetime(2026, 5, 1, 9, 12, 0, 123456, tzinfo=timezone.utc)
    assert entries[0].attributes == {"level": "error"}
    assert entries[0].tags == ["railway"]


def test_user_sample_csv_baseline_counts_when_available() -> None:
    sample_path = Path(
        os.environ.get(
            "SIGNALTHROTTLE_SAMPLE_CSV_PATH",
            r"C:\Users\INTEL\Downloads\logs.1777661104347.csv",
        )
    )
    if not sample_path.exists():
        pytest.skip("SignalThrottle sample CSV is not available on this machine")

    entries = engine_log_sync.parse_engine_log_entries(sample_path.read_text(encoding="utf-8"))
    parsed = [
        parse_signalthrottle(entry.message, entry.timestamp_utc)
        for entry in entries
        if entry.timestamp_utc is not None
    ]
    valid = [item for item in parsed if item is not None]
    pair_counts = Counter(item.symbol for item in valid)
    day_counts = Counter(item.timestamp_utc.date().isoformat() for item in valid)

    assert len(entries) == 4001
    assert len(valid) == 4001
    assert min(item.timestamp_utc for item in valid).isoformat().startswith("2026-04-30T07:33:23")
    assert max(item.timestamp_utc for item in valid).isoformat().startswith("2026-05-01T09:41:10")
    assert day_counts["2026-04-30"] == 763
    assert day_counts["2026-05-01"] == 3238
    assert pair_counts["EURJPY"] == 697
    assert pair_counts["USDJPY"] == 622
    assert pair_counts["GBPJPY"] == 512
    assert pair_counts["AUDJPY"] == 430
    assert pair_counts["CADJPY"] == 323
    assert pair_counts["EURAUD"] == 294
    assert pair_counts["GBPNZD"] == 242


def test_payload_to_log_text_accepts_json_list_payload() -> None:
    syncer = engine_log_sync.EngineLogSync(repo_factory=FakeSignalRepository)

    output = syncer._payload_to_log_text(
        [
            {
                "message": "[SignalThrottle] GBPUSD THROTTLED — 3 signals in last 300s (max 3)",
                "timestamp": "2026-04-27T07:15:23.169918856Z",
            },
            {
                "message": "[SignalThrottle] GBPUSD THROTTLED — 3 signals in last 300s (max 3)",
                "timestamp": "2026-04-27T07:15:27.593071262Z",
            },
        ]
    )

    assert '"message": "[SignalThrottle] GBPUSD THROTTLED' in output
    assert '"timestamp": "2026-04-27T07:15:23.169918856Z"' in output


def test_explain_sync_status_reports_missing_source() -> None:
    reason = engine_log_sync.explain_sync_status(
        {"status": "no_source_configured"},
        0,
    )

    assert reason == "engine_log_source_not_configured"
