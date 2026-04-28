from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import app.storage.repositories as repositories_module
from app.storage.repositories import (
    SignalRepository,
    _dedupe_exact_pressure_block_rows,
    _matches_signal_bucket,
    _merge_pressure_series,
    _select_latest_signal_rows,
)


def test_select_latest_signal_rows_keeps_latest_row_per_symbol() -> None:
    start_utc = datetime(2026, 4, 27, 7, 20, 36, tzinfo=timezone.utc)
    end_utc = datetime(2026, 4, 27, 7, 30, 3, tzinfo=timezone.utc)

    rows = [
        {
            "block_id": 23,
            "symbol": "GBPUSD",
            "start_utc": start_utc,
            "end_utc": end_utc,
            "pressure_grade": "B+",
        },
        {
            "block_id": 22,
            "symbol": "GBPUSD",
            "start_utc": start_utc,
            "end_utc": end_utc,
            "pressure_grade": "B+",
        },
        {
            "block_id": 9,
            "symbol": "EURCHF",
            "start_utc": datetime(2026, 4, 27, 6, 57, 22, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 15, 17, tzinfo=timezone.utc),
            "pressure_grade": "B+",
        },
    ]

    deduped = _select_latest_signal_rows(rows, bucket="all")

    assert len(deduped) == 2
    assert deduped[0]["block_id"] == 23
    assert deduped[1]["block_id"] == 9


def test_select_latest_signal_rows_collapses_overlapping_same_symbol_windows() -> None:
    rows = [
        {
            "block_id": 25,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 15, 23, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 25, 25, tzinfo=timezone.utc),
            "pressure_grade": "A-",
        },
        {
            "block_id": 23,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 20, 36, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 30, 3, tzinfo=timezone.utc),
            "pressure_grade": "B+",
        },
    ]

    deduped = _select_latest_signal_rows(rows, bucket="all")

    assert len(deduped) == 1
    assert deduped[0]["block_id"] == 23


def test_select_latest_signal_rows_with_limit_keeps_next_unique_symbol() -> None:
    start_1 = datetime(2026, 4, 27, 7, 20, 36, tzinfo=timezone.utc)
    end_1 = datetime(2026, 4, 27, 7, 30, 3, tzinfo=timezone.utc)
    start_2 = datetime(2026, 4, 27, 6, 57, 13, tzinfo=timezone.utc)
    end_2 = datetime(2026, 4, 27, 7, 14, 50, tzinfo=timezone.utc)

    rows = [
        {"block_id": 23, "symbol": "GBPUSD", "start_utc": start_1, "end_utc": end_1},
        {"block_id": 22, "symbol": "GBPUSD", "start_utc": start_1, "end_utc": end_1},
        {"block_id": 21, "symbol": "GBPUSD", "start_utc": start_1, "end_utc": end_1},
        {"block_id": 12, "symbol": "EURCHF", "start_utc": start_2, "end_utc": end_2},
    ]

    deduped = _select_latest_signal_rows(rows, bucket="all", limit=2)

    assert len(deduped) == 2
    assert deduped[0]["symbol"] == "GBPUSD"
    assert deduped[1]["symbol"] == "EURCHF"


def test_matches_signal_bucket_classifies_radar_watchlist_and_ready() -> None:
    radar = {"pressure_grade": "C", "trade_plan_id": None, "action": None, "execution_grade": None}
    watchlist = {"pressure_grade": "B+", "trade_plan_id": None, "action": None, "execution_grade": None}
    ready = {"pressure_grade": "A-", "trade_plan_id": 8, "action": "WAIT_BREAKDOWN_OR_RECLAIM", "execution_grade": "B+"}

    assert _matches_signal_bucket(radar, "radar") is True
    assert _matches_signal_bucket(watchlist, "watchlist") is True
    assert _matches_signal_bucket(ready, "ready") is True


def test_merge_pressure_series_merges_close_same_symbol_blocks() -> None:
    rows = [
        {
            "id": 11,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 15, 23, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 25, 25, tzinfo=timezone.utc),
            "event_count": 50,
            "max_gap_seconds": 22.0,
            "pressure_grade": "A-",
            "pressure_status": "SOFT_FINALIZED",
            "finalize_mode": "SOFT_FINALIZED",
            "is_active": False,
        },
        {
            "id": 12,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 25, 40, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 30, 3, tzinfo=timezone.utc),
            "event_count": 63,
            "max_gap_seconds": 14.58,
            "pressure_grade": "B+",
            "pressure_status": "ACTIVE",
            "finalize_mode": None,
            "is_active": True,
        },
    ]

    merged = _merge_pressure_series(rows, merge_gap_seconds=300)

    assert len(merged) == 1
    assert merged[0]["symbol"] == "GBPUSD"
    assert merged[0]["block_count"] == 2
    assert merged[0]["event_count"] == 113
    assert merged[0]["latest_block_id"] == 12
    assert merged[0]["best_pressure_grade"] == "A-"


def test_merge_pressure_series_keeps_separate_series_after_hard_gap() -> None:
    rows = [
        {
            "id": 20,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 15, 23, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 20, 23, tzinfo=timezone.utc),
            "event_count": 30,
            "max_gap_seconds": 18.0,
            "pressure_grade": "B+",
            "pressure_status": "HARD_FINALIZED",
            "finalize_mode": "HARD_FINALIZED",
            "is_active": False,
        },
        {
            "id": 21,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 26, 0, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 31, 0, tzinfo=timezone.utc),
            "event_count": 35,
            "max_gap_seconds": 16.0,
            "pressure_grade": "B+",
            "pressure_status": "ACTIVE",
            "finalize_mode": None,
            "is_active": True,
        },
    ]

    merged = _merge_pressure_series(rows, merge_gap_seconds=300)

    assert len(merged) == 2
    assert {row["latest_block_id"] for row in merged} == {20, 21}


def test_merge_pressure_series_keeps_continuity_split_blocks_in_one_series() -> None:
    rows = [
        {
            "id": 30,
            "symbol": "NZDCHF",
            "start_utc": datetime(2026, 4, 22, 13, 0, 28, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 22, 13, 2, 2, tzinfo=timezone.utc),
            "event_count": 19,
            "max_gap_seconds": 7.2,
            "pressure_grade": "FAILED_MIN_DURATION",
            "pressure_status": "SOFT_FINALIZED",
            "finalize_mode": "CONTINUITY_SPLIT",
            "is_active": False,
        },
        {
            "id": 31,
            "symbol": "NZDCHF",
            "start_utc": datetime(2026, 4, 22, 13, 6, 27, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 22, 13, 14, 3, tzinfo=timezone.utc),
            "event_count": 85,
            "max_gap_seconds": 21.73,
            "pressure_grade": "B+",
            "pressure_status": "SOFT_FINALIZED",
            "finalize_mode": "SOFT_FINALIZED",
            "is_active": False,
        },
    ]

    merged = _merge_pressure_series(rows, merge_gap_seconds=300)

    assert len(merged) == 1
    assert merged[0]["block_count"] == 2
    assert merged[0]["latest_block_id"] == 31
    assert merged[0]["best_pressure_grade"] == "B+"
    assert merged[0]["best_valid_block_grade"] == "B+"
    assert merged[0]["series_reason"] == "SPLIT_BY_CONTINUITY_GAP"


def test_merge_pressure_series_best_valid_block_grade_ignores_failed_blocks() -> None:
    rows = [
        {
            "id": 30,
            "symbol": "NZDCHF",
            "start_utc": datetime(2026, 4, 22, 13, 0, 28, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 22, 13, 2, 2, tzinfo=timezone.utc),
            "event_count": 19,
            "max_gap_seconds": 7.2,
            "pressure_grade": "FAILED_MIN_DURATION",
            "pressure_status": "SOFT_FINALIZED",
            "finalize_mode": "CONTINUITY_SPLIT",
            "is_active": False,
        },
        {
            "id": 31,
            "symbol": "NZDCHF",
            "start_utc": datetime(2026, 4, 22, 13, 6, 27, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 22, 13, 14, 3, tzinfo=timezone.utc),
            "event_count": 85,
            "max_gap_seconds": 21.73,
            "pressure_grade": "B+",
            "pressure_status": "SOFT_FINALIZED",
            "finalize_mode": "SOFT_FINALIZED",
            "is_active": False,
        },
    ]

    merged = _merge_pressure_series(rows, merge_gap_seconds=300)

    assert len(merged) == 1
    assert merged[0]["best_pressure_grade"] == "B+"
    assert merged[0]["best_valid_block_grade"] == "B+"


def test_merge_pressure_series_marks_replay_gap_family_as_continuity_split() -> None:
    rows = [
        {
            "id": 32,
            "symbol": "NZDCHF",
            "start_utc": datetime(2026, 4, 22, 13, 0, 0, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 22, 13, 0, 50, tzinfo=timezone.utc),
            "event_count": 6,
            "max_gap_seconds": 10.0,
            "pressure_grade": "FAILED_MIN_DURATION",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "is_active": False,
        },
        {
            "id": 33,
            "symbol": "NZDCHF",
            "start_utc": datetime(2026, 4, 22, 13, 3, 30, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 22, 13, 8, 30, tzinfo=timezone.utc),
            "event_count": 31,
            "max_gap_seconds": 10.0,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "is_active": False,
        },
    ]

    merged = _merge_pressure_series(rows, merge_gap_seconds=300)

    assert len(merged) == 1
    assert merged[0]["block_count"] == 2
    assert merged[0]["best_valid_block_grade"] == "B+"
    assert merged[0]["series_reason"] == "SPLIT_BY_CONTINUITY_GAP"


def test_upsert_live_block_from_event_splits_on_continuity_gap_but_not_hard_gap(monkeypatch) -> None:
    class FakeRepo:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def finalize_other_active_blocks_on_pair_replacement(self, symbol: str) -> None:
            self.calls.append(("pair_replacement", symbol))

        async def get_active_block(self, symbol: str) -> dict | None:
            return {
                "id": 10,
                "symbol": symbol,
                "start_utc": datetime(2026, 4, 22, 13, 0, 28, tzinfo=timezone.utc),
                "end_utc": datetime(2026, 4, 22, 13, 2, 2, tzinfo=timezone.utc),
                "previous_block_id": 7,
            }

        async def mark_block_hard_finalized(self, block_id: int) -> None:
            self.calls.append(("hard_finalize", block_id))

        async def mark_block_continuity_split(self, block_id: int) -> None:
            self.calls.append(("continuity_split", block_id))

        async def get_last_finalized_block(self, symbol: str) -> dict | None:
            return {"id": 10}

        async def get_signal_events_in_range(self, symbol: str, start_utc: datetime, end_utc: datetime):
            return [
                repositories_module.LogEvent(
                    symbol=symbol,
                    event_type="SIGNAL_THROTTLE",
                    timestamp_utc=start_utc,
                    raw_message="start",
                ),
                repositories_module.LogEvent(
                    symbol=symbol,
                    event_type="SIGNAL_THROTTLE",
                    timestamp_utc=end_utc,
                    raw_message="end",
                ),
            ]

        async def upsert_active_block(self, **kwargs) -> dict:
            self.calls.append(("upsert_active_block", kwargs))
            return {"id": 11, "action": "created"}

    fake_repo = FakeRepo()
    event = repositories_module.LogEvent(
        symbol="NZDCHF",
        event_type="SIGNAL_THROTTLE",
        timestamp_utc=datetime(2026, 4, 22, 13, 6, 27, tzinfo=timezone.utc),
        raw_message="test",
    )

    monkeypatch.setattr(repositories_module.settings, "max_continuity_gap_seconds", 90)

    result = asyncio.run(
        SignalRepository.upsert_live_block_from_event(
            fake_repo,
            event,
            max_event_gap_seconds=300,
            chart_offset_hours=3,
        )
    )

    assert result == {"id": 11, "action": "created"}
    assert ("continuity_split", 10) in fake_repo.calls
    assert not any(call[0] == "hard_finalize" for call in fake_repo.calls)
    upsert_call = next(call for call in fake_repo.calls if call[0] == "upsert_active_block")
    assert upsert_call[1]["start_utc"] == event.timestamp_utc
    assert upsert_call[1]["previous_block_id"] == 10


def test_merge_pressure_series_dedupes_identical_replay_rows_and_preserves_max_event_count() -> None:
    rows = [
        {
            "id": 10,
            "symbol": "EURCHF",
            "start_utc": datetime(2026, 4, 27, 6, 57, 13, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 14, 50, tzinfo=timezone.utc),
            "duration_minutes": 17.62,
            "event_count": 117,
            "max_gap_seconds": 61.0,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "is_active": False,
        },
        {
            "id": 11,
            "symbol": "EURCHF",
            "start_utc": datetime(2026, 4, 27, 6, 57, 13, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 14, 50, tzinfo=timezone.utc),
            "duration_minutes": 17.62,
            "event_count": 117,
            "max_gap_seconds": 61.0,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "is_active": False,
        },
        {
            "id": 12,
            "symbol": "EURCHF",
            "start_utc": datetime(2026, 4, 27, 6, 57, 13, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 14, 50, tzinfo=timezone.utc),
            "duration_minutes": 17.62,
            "event_count": 117,
            "max_gap_seconds": 61.0,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "is_active": False,
        },
        {
            "id": 9,
            "symbol": "EURCHF",
            "start_utc": datetime(2026, 4, 27, 6, 57, 22, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 15, 17, tzinfo=timezone.utc),
            "duration_minutes": 17.92,
            "event_count": 118,
            "max_gap_seconds": 61.0,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "is_active": False,
        },
    ]

    merged = _merge_pressure_series(rows, merge_gap_seconds=300)

    assert len(merged) == 1
    assert merged[0]["start_utc"] == datetime(2026, 4, 27, 6, 57, 13, tzinfo=timezone.utc)
    assert merged[0]["end_utc"] == datetime(2026, 4, 27, 7, 15, 17, tzinfo=timezone.utc)
    assert merged[0]["event_count"] == 118
    assert merged[0]["block_count"] == 1
    assert merged[0]["latest_block_id"] == 9


def test_select_latest_signal_rows_uses_one_series_for_overlapping_replay_blocks() -> None:
    rows = [
        {
            "block_id": 12,
            "symbol": "EURCHF",
            "start_utc": datetime(2026, 4, 27, 6, 57, 13, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 14, 50, tzinfo=timezone.utc),
            "duration_minutes": 17.62,
            "event_count": 117,
            "density_per_minute": 6.64,
            "max_gap_seconds": 61.0,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "trade_plan_id": None,
            "execution_grade": None,
            "action": None,
        },
        {
            "block_id": 9,
            "symbol": "EURCHF",
            "start_utc": datetime(2026, 4, 27, 6, 57, 22, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 15, 17, tzinfo=timezone.utc),
            "duration_minutes": 17.92,
            "event_count": 118,
            "density_per_minute": 6.58,
            "max_gap_seconds": 61.0,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "trade_plan_id": None,
            "execution_grade": None,
            "action": None,
        },
    ]

    deduped = _select_latest_signal_rows(rows, bucket="watchlist")

    assert len(deduped) == 1
    assert deduped[0]["block_id"] == 9
    assert deduped[0]["event_count"] == 118
    assert deduped[0]["block_count"] == 1
    assert deduped[0]["start_utc"] == datetime(2026, 4, 27, 6, 57, 13, tzinfo=timezone.utc)
    assert deduped[0]["end_utc"] == datetime(2026, 4, 27, 7, 15, 17, tzinfo=timezone.utc)


def test_repository_latest_signals_sql_surfaces_reason_code_fallback(monkeypatch) -> None:
    rows = [
        {
            "id": None,
            "trade_plan_id": None,
            "block_id": 9,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 20, 36, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 30, 3, tzinfo=timezone.utc),
            "duration_minutes": 9.45,
            "event_count": 113,
            "density_per_minute": 11.96,
            "max_gap_seconds": 14.58,
            "avg_gap_seconds": 5.06,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "is_active": False,
            "execution_grade": None,
            "execution_side": None,
            "chart_phase": None,
            "reason_code": "TRADE_PLAN_REQUIRED",
            "action": None,
            "entry_zone": None,
            "invalidation": None,
            "message": None,
            "signal_bucket": None,
            "trade_plan_pressure_status": None,
            "trade_plan_status": "TRADE_PLAN_REQUIRED",
            "market_context_status": "PENDING_OR_FAILED",
            "pending_reason": None,
            "dashboard_bucket": "watchlist_trade_plan_pending",
            "owner_alert": "PENDING",
            "display_message": "GBPUSD B+ pressure is valid. Trade plan is required.",
            "trade_plan_required": True,
        }
    ]

    class FakeCursor:
        executed_sql: str = ""

        async def execute(self, query, params=None) -> None:
            FakeCursor.executed_sql = str(query)

        async def fetchall(self) -> list[dict]:
            return rows

    @asynccontextmanager
    async def fake_get_cursor():
        yield FakeCursor()

    monkeypatch.setattr(repositories_module, "get_cursor", fake_get_cursor)

    repo = SignalRepository()
    result = asyncio.run(repo.get_latest_signals(limit=10, bucket="watchlist"))

    assert "AS reason_code" in FakeCursor.executed_sql
    assert "COALESCE(" in FakeCursor.executed_sql
    assert result[0]["reason_code"] == "TRADE_PLAN_REQUIRED"


def test_dedupe_exact_pressure_block_rows_prefers_latest_duplicate_row() -> None:
    rows = [
        {
            "id": 13,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 20, 36, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 30, 3, tzinfo=timezone.utc),
            "duration_minutes": 9.45,
            "event_count": 113,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "trade_plan_id": None,
        },
        {
            "id": 23,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 20, 36, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 30, 3, tzinfo=timezone.utc),
            "duration_minutes": 9.45,
            "event_count": 113,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "trade_plan_id": None,
        },
    ]

    deduped = _dedupe_exact_pressure_block_rows(rows)

    assert len(deduped) == 1
    assert deduped[0]["id"] == 23


def test_get_signal_series_detail_dedupes_exact_raw_blocks(monkeypatch) -> None:
    series_row = {
        "symbol": "GBPUSD",
        "start_utc": datetime(2026, 4, 27, 7, 15, 23, tzinfo=timezone.utc),
        "end_utc": datetime(2026, 4, 27, 7, 30, 3, tzinfo=timezone.utc),
        "latest_block_id": 23,
        "latest_trade_plan_id": None,
        "block_ids": [23],
    }
    latest_snapshot = {"block_id": 23, "chart_phase": "PIVOT_RECLAIM_CONTINUATION"}
    raw_blocks = [
        {
            "id": 13,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 20, 36, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 30, 3, tzinfo=timezone.utc),
            "duration_minutes": 9.45,
            "event_count": 113,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "trade_plan_id": None,
        },
        {
            "id": 23,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 20, 36, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 30, 3, tzinfo=timezone.utc),
            "duration_minutes": 9.45,
            "event_count": 113,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "trade_plan_id": None,
        },
        {
            "id": 25,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 15, 23, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 25, 25, tzinfo=timezone.utc),
            "duration_minutes": 10.03,
            "event_count": 117,
            "pressure_grade": "A-",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "trade_plan_id": None,
        },
        {
            "id": 28,
            "symbol": "GBPUSD",
            "start_utc": datetime(2026, 4, 27, 7, 15, 23, tzinfo=timezone.utc),
            "end_utc": datetime(2026, 4, 27, 7, 24, 55, tzinfo=timezone.utc),
            "duration_minutes": 9.53,
            "event_count": 112,
            "pressure_grade": "B+",
            "pressure_status": "REPLAY",
            "finalize_mode": "REPLAY_FINALIZE",
            "trade_plan_id": None,
        },
    ]

    class FakeCursor:
        def __init__(self, fetchone_responses=None, fetchall_responses=None):
            self._fetchone_responses = list(fetchone_responses or [])
            self._fetchall_responses = list(fetchall_responses or [])

        async def execute(self, query, params=None) -> None:
            return None

        async def fetchone(self):
            if self._fetchone_responses:
                return self._fetchone_responses.pop(0)
            return None

        async def fetchall(self):
            if self._fetchall_responses:
                return self._fetchall_responses.pop(0)
            return []

    cursors = [
        FakeCursor(fetchone_responses=[series_row]),
        FakeCursor(fetchone_responses=[latest_snapshot]),
        FakeCursor(fetchall_responses=[raw_blocks]),
    ]

    @asynccontextmanager
    async def fake_get_cursor():
        yield cursors.pop(0)

    async def fake_refresh_pressure_series(self, symbol: str | None = None) -> None:
        return None

    monkeypatch.setattr(repositories_module, "get_cursor", fake_get_cursor)
    monkeypatch.setattr(SignalRepository, "refresh_pressure_series", fake_refresh_pressure_series)

    repo = SignalRepository()
    detail = asyncio.run(repo.get_signal_series_detail("GBPUSD"))

    assert detail is not None
    assert len(detail["blocks"]) == 1
    assert [block["id"] for block in detail["blocks"]] == [23]
