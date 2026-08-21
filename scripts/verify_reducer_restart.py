from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.contracts.observer_telemetry import (
    OBSERVER_TELEMETRY_SCHEMA_VERSION,
    ObserverTelemetryEvent,
    TelemetryIntakeStatus,
)
from app.services.reducer_worker import DurableReducerWorker, ReducerRunStatus
from app.services.telemetry_intake import TelemetryIntakeService
from app.storage.postgres import close_db, get_connection
from app.storage.reducer_jobs import ReducerJobRepository


async def main() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        raise RuntimeError("TEST_DATABASE_URL is required")
    settings.database_url = database_url
    settings.database_pool_min_size = 1
    settings.database_pool_max_size = 3

    event = ObserverTelemetryEvent(
        event_id=uuid4(),
        stream_id=f"restart:{uuid4()}",
        event_type="SIGNAL_THROTTLE",
        source_authority="LEGACY_OBSERVATIONAL",
        schema_version=OBSERVER_TELEMETRY_SCHEMA_VERSION,
        occurred_at_utc=datetime.now(UTC),
        payload={"gate": "db-restart-same-process"},
    )
    intake = TelemetryIntakeService()
    accepted = await intake.ingest(event)
    if accepted.status != TelemetryIntakeStatus.ACCEPTED:
        raise RuntimeError(f"unexpected intake status: {accepted.status}")

    jobs = ReducerJobRepository()
    abandoned = await jobs.claim_next(
        lease_owner="pre-restart-worker",
        lease_duration=timedelta(seconds=1),
    )
    if abandoned is None:
        raise RuntimeError("no reducer job was available before restart")

    print("READY_FOR_DATABASE_RESTART", flush=True)
    await asyncio.to_thread(input)

    recovered = await jobs.claim_next(
        lease_owner="post-restart-worker",
        lease_duration=timedelta(seconds=30),
    )
    if recovered is None or recovered.reducer_job_id != abandoned.reducer_job_id:
        raise RuntimeError("expired lease was not recovered after database restart")
    result = await DurableReducerWorker(
        lease_owner="post-restart-processor"
    ).process_claim(recovered)
    if result.status != ReducerRunStatus.DONE:
        raise RuntimeError(f"recovered reducer did not finish: {result.status}")

    async with get_connection() as conn:
        row = await (
            await conn.execute(
                """
                SELECT COUNT(*) AS output_count
                FROM observer_plane.reducer_outputs
                WHERE reducer_job_id = %s
                """,
                (abandoned.reducer_job_id,),
            )
        ).fetchone()
    if row is None or row["output_count"] != 1:
        raise RuntimeError("restart recovery produced a missing or duplicate output")

    await close_db()
    print("DB_RESTART_SAME_PROCESS=PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
