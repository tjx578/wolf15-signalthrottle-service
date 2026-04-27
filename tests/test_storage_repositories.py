from __future__ import annotations

from datetime import datetime, timezone

from app.storage.repositories import _dedupe_latest_signal_rows


def test_dedupe_latest_signal_rows_keeps_newest_block_per_symbol_window() -> None:
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

    deduped = _dedupe_latest_signal_rows(rows)

    assert len(deduped) == 2
    assert deduped[0]["block_id"] == 23
    assert deduped[1]["block_id"] == 9


def test_dedupe_latest_signal_rows_keeps_distinct_windows_for_same_symbol() -> None:
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

    deduped = _dedupe_latest_signal_rows(rows)

    assert len(deduped) == 2
    assert {row["block_id"] for row in deduped} == {23, 25}