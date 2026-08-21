from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.detector.finalizer import SignalFinalizer, determine_finalize_mode


class FakeSignalRepository:
    def __init__(self, blocks: list[dict]) -> None:
        self.blocks = blocks
        self.cooling_ids: list[int] = []
        self.soft_ids: list[int] = []
        self.hard_ids: list[int] = []

    async def get_active_or_cooling_blocks(self) -> list[dict]:
        return self.blocks

    async def mark_block_cooling(self, block_id: int) -> None:
        self.cooling_ids.append(block_id)

    async def mark_block_soft_finalized(self, block_id: int) -> None:
        self.soft_ids.append(block_id)

    async def mark_block_hard_finalized(self, block_id: int) -> None:
        self.hard_ids.append(block_id)


def test_determine_finalize_mode_states() -> None:
    now = datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)

    assert determine_finalize_mode(now - timedelta(seconds=10), now) == "ACTIVE"
    assert determine_finalize_mode(now - timedelta(seconds=45), now) == "COOLING"
    assert determine_finalize_mode(now - timedelta(seconds=120), now) == "SOFT_FINALIZED"
    assert determine_finalize_mode(now - timedelta(seconds=360), now) == "HARD_FINALIZED"


def test_finalizer_marks_cooling() -> None:
    now = datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)
    repo = FakeSignalRepository(
        [
            {
                "id": 1,
                "symbol": "USDJPY",
                "end_utc": now - timedelta(seconds=45),
                "pressure_status": "ACTIVE",
            }
        ]
    )
    finalizer = SignalFinalizer(repo=repo)

    asyncio.run(finalizer.finalize_due_blocks(now_utc=now))

    assert repo.cooling_ids == [1]
    assert repo.soft_ids == []
    assert repo.hard_ids == []


def test_finalizer_soft_finalizes_without_phase2_enrichment() -> None:
    now = datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)
    repo = FakeSignalRepository(
        [
            {
                "id": 2,
                "symbol": "USDJPY",
                "end_utc": now - timedelta(seconds=120),
                "pressure_status": "COOLING",
                "pressure_grade": "B+",
            }
        ]
    )
    finalizer = SignalFinalizer(repo=repo)
    asyncio.run(finalizer.finalize_due_blocks(now_utc=now))

    assert repo.soft_ids == [2]
    assert repo.hard_ids == []


def test_finalizer_hard_finalizes() -> None:
    now = datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)
    repo = FakeSignalRepository(
        [
            {
                "id": 3,
                "symbol": "GBPUSD",
                "end_utc": now - timedelta(seconds=360),
                "pressure_status": "COOLING",
            }
        ]
    )
    finalizer = SignalFinalizer(repo=repo)

    asyncio.run(finalizer.finalize_due_blocks(now_utc=now))

    assert repo.hard_ids == [3]
