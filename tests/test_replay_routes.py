from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app.api.routes_replay as routes_replay
import app.api.routes_signals as routes_signals
import app.lifecycle as lifecycle
from app.main import create_app


class FakeSignalRepository:
    trade_plans: list[dict] = []
    signal_event_id = 0
    block_id = 0
    trade_plan_id = 0
    blocks_by_hash: dict[str, dict] = {}

    @classmethod
    def reset(cls) -> None:
        cls.trade_plans = []
        cls.signal_event_id = 0
        cls.block_id = 0
        cls.trade_plan_id = 0
        cls.blocks_by_hash = {}

    async def insert_signal_event(self, **kwargs) -> dict:
        self.__class__.signal_event_id += 1
        return {"id": self.__class__.signal_event_id, "duplicate": False}

    async def upsert_active_block(self, **kwargs) -> dict:
        self.__class__.block_id += 1
        return {"id": self.__class__.block_id, "action": "created"}

    async def upsert_pressure_block_by_hash(self, **kwargs) -> dict:
        block_hash = kwargs.get("block_hash") or ""
        existing = self.__class__.blocks_by_hash.get(block_hash)
        if existing is not None:
            # Idempotent path: same hash returns the same block id without
            # increasing the block counter (mirrors the SQL ON CONFLICT path).
            return {
                "id": existing["id"],
                "action": "unchanged",
                "block_hash": block_hash,
                "pressure_status": existing["pressure_status"],
                "pressure_grade": existing["pressure_grade"],
            }
        self.__class__.block_id += 1
        record = {
            "id": self.__class__.block_id,
            "action": "created",
            "block_hash": block_hash,
            "pressure_status": kwargs.get("pressure_status"),
            "pressure_grade": kwargs.get("pressure_grade"),
        }
        self.__class__.blocks_by_hash[block_hash] = record
        return record

    async def finalize_block(self, block_id: int, finalize_mode: str) -> None:
        return None

    async def get_trade_plan_for_block(self, block_id: int) -> dict | None:
        for plan in reversed(self.__class__.trade_plans):
            if plan["block_id"] == block_id:
                return plan
        return None

    async def insert_trade_plan(self, block_id: int, plan: dict) -> int:
        self.__class__.trade_plan_id += 1
        record = {"id": self.__class__.trade_plan_id, "block_id": block_id, **plan}
        self.__class__.trade_plans.append(record)
        return self.__class__.trade_plan_id

    async def get_latest_trade_plans(
        self,
        limit: int = 20,
        bucket: str = "all",
    ) -> list[dict]:
        plans = list(reversed(self.__class__.trade_plans))
        if bucket == "actionable":
            plans = [
                plan
                for plan in plans
                if plan.get("execution_grade") in {"A+", "A"}
                and plan.get("action") != "NO_TRADE_WAIT_CONTEXT"
            ]
        elif bucket == "watchlist":
            plans = [
                plan
                for plan in plans
                if plan.get("execution_grade") in {"B", "B+", "C"}
                or plan.get("action") == "NO_TRADE_WAIT_CONTEXT"
            ]
        return plans[:limit]

    async def get_latest_signals(self, limit: int = 50, bucket: str = "watchlist") -> list[dict]:
        plans = list(reversed(self.__class__.trade_plans))
        return plans[:limit]


async def _noop() -> None:
    return None


async def fake_enrich_block_with_market_context(block: dict, repo: FakeSignalRepository):
    plan = {
        "symbol": block["symbol"],
        "pressure_grade": block["pressure_grade"],
        "execution_grade": "A",
        "execution_side": "BUY",
        "action": "BUY_PULLBACK",
        "message": f"Plan for {block['symbol']}",
    }
    plan_id = await repo.insert_trade_plan(block["id"], plan)
    plan["id"] = plan_id
    plan["block_id"] = block["id"]
    return plan


def test_replay_logs_creates_trade_plan_and_latest_signal(monkeypatch) -> None:
    FakeSignalRepository.reset()
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_replay, "SignalRepository", FakeSignalRepository)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)
    monkeypatch.setattr(
        routes_replay,
        "enrich_block_with_market_context",
        fake_enrich_block_with_market_context,
    )

    app = create_app()
    client = TestClient(app)
    logs = Path("tests/fixtures/usdjpy_bplus_replay.log").read_text(encoding="utf-8")

    replay_response = client.post("/replay/logs", json={"logs": logs})
    assert replay_response.status_code == 200
    replay_payload = replay_response.json()
    assert replay_payload["status"] == "processed"
    assert replay_payload["canonical_blocks_detected"] == 1
    assert replay_payload["trade_plans_created"] == 1
    assert replay_payload["blocks"][0]["pressure_grade"] == "B+"
    assert replay_payload["blocks"][0]["trade_plan_created"] is True

    latest_response = client.get("/signals/latest")
    assert latest_response.status_code == 200
    latest_payload = latest_response.json()
    assert latest_payload["count"] == 1
    assert latest_payload["signals"][0]["symbol"] == "USDJPY"
    assert latest_payload["signals"][0]["pressure_grade"] == "B+"


def test_replay_logs_accepts_structured_json_lines(monkeypatch) -> None:
    FakeSignalRepository.reset()
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_replay, "SignalRepository", FakeSignalRepository)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)
    monkeypatch.setattr(
        routes_replay,
        "enrich_block_with_market_context",
        fake_enrich_block_with_market_context,
    )

    app = create_app()
    client = TestClient(app)
    logs = "\n".join(
        [
            '{"message":"[SignalThrottle] GBPUSD THROTTLED — 3 signals in last 300s (max 3)","severity":"error","attributes":{"level":"error"},"timestamp":"2026-04-27T07:15:23.169918856Z"}',
            '{"message":"[SignalThrottle] GBPUSD THROTTLED — 3 signals in last 300s (max 3)","severity":"error","attributes":{"level":"error"},"timestamp":"2026-04-27T07:19:55.093229711Z"}',
        ]
    )

    replay_response = client.post("/replay/logs", json={"logs": logs})

    assert replay_response.status_code == 200
    replay_payload = replay_response.json()
    assert replay_payload["status"] == "processed"
    assert replay_payload["events_parsed"] == 2
    assert replay_payload["canonical_blocks_detected"] == 2
    assert replay_payload["blocks"][0]["symbol"] == "GBPUSD"

def test_replay_logs_is_idempotent_at_block_level(monkeypatch) -> None:
    """Replaying the same fixture twice MUST NOT create duplicate
    pressure_blocks. The block_hash unique index enforces this at the
    storage layer; the route should report the second pass as
    canonical_blocks_detected==1 with blocks_created==0 and the existing
    block id reused."""
    FakeSignalRepository.reset()
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_replay, "SignalRepository", FakeSignalRepository)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)
    monkeypatch.setattr(
        routes_replay,
        "enrich_block_with_market_context",
        fake_enrich_block_with_market_context,
    )

    app = create_app()
    client = TestClient(app)
    logs = Path("tests/fixtures/usdjpy_bplus_replay.log").read_text(encoding="utf-8")

    first = client.post("/replay/logs", json={"logs": logs}).json()
    blocks_after_first = FakeSignalRepository.block_id
    hashes_after_first = set(FakeSignalRepository.blocks_by_hash.keys())

    second = client.post("/replay/logs", json={"logs": logs}).json()

    assert first["status"] == "processed"
    assert second["status"] == "processed"
    # Same canonical detection on both passes.
    assert first["canonical_blocks_detected"] == second["canonical_blocks_detected"]
    # The hash registry must not grow on the second pass.
    assert FakeSignalRepository.blocks_by_hash.keys() == hashes_after_first
    # No additional block ids consumed on the second pass.
    assert FakeSignalRepository.block_id == blocks_after_first
    # All second-pass blocks should report the unchanged action.
    actions = {b.get("action") for b in second["blocks"]}
    assert actions == {"unchanged"}


def test_replay_logs_splits_continuity_gap_into_two_blocks_same_family(monkeypatch) -> None:
    FakeSignalRepository.reset()
    monkeypatch.setattr(lifecycle, "init_db", _noop)
    monkeypatch.setattr(lifecycle, "run_migrations", _noop)
    monkeypatch.setattr(lifecycle, "close_db", _noop)
    monkeypatch.setattr(routes_replay, "SignalRepository", FakeSignalRepository)
    monkeypatch.setattr(routes_signals, "SignalRepository", FakeSignalRepository)
    monkeypatch.setattr(
        routes_replay,
        "enrich_block_with_market_context",
        fake_enrich_block_with_market_context,
    )
    monkeypatch.setattr(routes_replay.settings, "max_continuity_gap_seconds", 90)

    first_run = [
        f"2026-04-22T13:00:{second:02d}Z [SignalThrottle] NZDCHF THROTTLED — 3 signals in last 300s (max 3)"
        for second in (0, 10, 20, 30, 40, 50)
    ]
    second_run = [
        f"2026-04-22T13:{minute:02d}:{second:02d}Z [SignalThrottle] NZDCHF THROTTLED — 3 signals in last 300s (max 3)"
        for minute, second in [
            (3, 30), (3, 40), (3, 50),
            (4, 0), (4, 10), (4, 20),
            (4, 30), (4, 40), (4, 50),
            (5, 0), (5, 10), (5, 20),
            (5, 30), (5, 40), (5, 50),
            (6, 0), (6, 10), (6, 20),
            (6, 30), (6, 40), (6, 50),
            (7, 0), (7, 10), (7, 20),
            (7, 30), (7, 40), (7, 50),
            (8, 0), (8, 10), (8, 20),
            (8, 30),
        ]
    ]
    logs = "\n".join(first_run + second_run)

    app = create_app()
    client = TestClient(app)
    replay_response = client.post("/replay/logs", json={"logs": logs})

    assert replay_response.status_code == 200
    replay_payload = replay_response.json()
    assert replay_payload["status"] == "processed"
    assert replay_payload["canonical_blocks_detected"] == 2
    grades = [block["pressure_grade"] for block in replay_payload["blocks"]]
    assert grades == ["FAILED_MIN_DURATION", "B+"]
