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

    @classmethod
    def reset(cls) -> None:
        cls.trade_plans = []
        cls.signal_event_id = 0
        cls.block_id = 0
        cls.trade_plan_id = 0

    async def insert_signal_event(self, **kwargs) -> dict:
        self.__class__.signal_event_id += 1
        return {"id": self.__class__.signal_event_id, "duplicate": False}

    async def upsert_active_block(self, **kwargs) -> dict:
        self.__class__.block_id += 1
        return {"id": self.__class__.block_id, "action": "created"}

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
    assert replay_payload["blocks_detected"] == 1
    assert replay_payload["trade_plans_created"] == 1
    assert replay_payload["blocks"][0]["pressure_grade"] == "B+"
    assert replay_payload["blocks"][0]["trade_plan_created"] is True

    latest_response = client.get("/signals/latest")
    assert latest_response.status_code == 200
    latest_payload = latest_response.json()
    assert latest_payload["count"] == 1
    assert latest_payload["signals"][0]["symbol"] == "USDJPY"
    assert latest_payload["signals"][0]["pressure_grade"] == "B+"