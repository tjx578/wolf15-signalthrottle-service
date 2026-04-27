from __future__ import annotations

from datetime import datetime, timezone

from app.storage.repositories import (
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
    assert deduped[0]["block_id"] == 25


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