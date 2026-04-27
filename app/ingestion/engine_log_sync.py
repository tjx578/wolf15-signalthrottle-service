from __future__ import annotations

import logging
import re
from datetime import datetime, time, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx

from ..config import settings
from ..models.log_event import LogEvent
from ..parser.signalthrottle_parser import parse_signalthrottle
from ..parser.timestamp_mapper import to_chart_time, to_wita
from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)

_TS_RE = re.compile(r"(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)")


def owner_day_window_utc(
    now_utc: datetime,
    owner_timezone: str,
) -> tuple[datetime, datetime]:
    owner_tz = ZoneInfo(owner_timezone)
    localized_now = now_utc.astimezone(owner_tz)
    start_local = datetime.combine(localized_now.date(), time.min, tzinfo=owner_tz)
    return start_local.astimezone(timezone.utc), now_utc.astimezone(timezone.utc)


class EngineLogSync:
    def __init__(
        self,
        *,
        repo_factory: Callable[[], SignalRepository] = SignalRepository,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo_factory = repo_factory
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    async def sync_today(self) -> dict[str, Any]:
        if not settings.engine_log_sync_enabled:
            return {"status": "disabled"}

        if not settings.engine_log_source_url:
            return {"status": "no_source_configured"}

        now_utc = self._now_provider()
        start_utc, end_utc = owner_day_window_utc(now_utc, settings.owner_timezone)
        raw_logs = await self.fetch_logs(start_utc, end_utc)
        if not raw_logs.strip():
            return {
                "status": "no_logs",
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
            }

        result = await self.ingest_logs(raw_logs)
        result.update(
            {
                "status": "ok",
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
            }
        )
        return result

    async def fetch_logs(self, start_utc: datetime, end_utc: datetime) -> str:
        headers: dict[str, str] = {}
        if settings.engine_log_source_token:
            headers["Authorization"] = f"Bearer {settings.engine_log_source_token}"

        params = {
            "start_utc": start_utc.isoformat().replace("+00:00", "Z"),
            "end_utc": end_utc.isoformat().replace("+00:00", "Z"),
            "contains": "SignalThrottle",
        }

        async with httpx.AsyncClient(timeout=settings.engine_log_sync_timeout_seconds) as client:
            response = await client.get(
                settings.engine_log_source_url,
                params=params,
                headers=headers,
            )
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = response.json()
            if isinstance(payload, dict):
                if isinstance(payload.get("logs"), str):
                    return payload["logs"]
                if isinstance(payload.get("lines"), list):
                    return "\n".join(str(item) for item in payload["lines"])
            return ""

        return response.text

    async def ingest_logs(self, raw_logs: str) -> dict[str, Any]:
        repo = self._repo_factory()
        stored = 0
        duplicates = 0
        parsed_count = 0

        events = sorted(self._parse_events(raw_logs), key=lambda event: event.timestamp_utc)
        for event in events:
            parsed_count += 1
            result = await repo.insert_signal_event(
                symbol=event.symbol,
                event_type=event.event_type,
                timestamp_utc=event.timestamp_utc,
                raw_message=event.raw_message,
                source_service=event.source_service,
                timestamp_wita=event.timestamp_wita,
                chart_time=event.chart_time,
                meta={"sync_source": "engine_log_sync"},
            )
            if result.get("duplicate"):
                duplicates += 1
                continue

            stored += 1
            await repo.upsert_live_block_from_event(
                event,
                max_event_gap_seconds=settings.max_event_gap_seconds,
                chart_offset_hours=settings.chart_time_offset_hours,
            )

        return {
            "events_parsed": parsed_count,
            "events_stored": stored,
            "duplicates_skipped": duplicates,
        }

    def _parse_events(self, raw_logs: str) -> list[LogEvent]:
        events: list[LogEvent] = []
        for raw_line in raw_logs.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            ts_match = _TS_RE.search(line)
            if not ts_match:
                continue

            ts_str = ts_match.group("ts")
            if not ts_str.endswith("Z"):
                ts_str += "Z"

            try:
                ts_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            parsed = parse_signalthrottle(raw_message=line, timestamp_utc=ts_utc)
            if not parsed:
                continue

            events.append(
                LogEvent(
                    symbol=parsed.symbol,
                    event_type="SIGNAL_THROTTLE",
                    timestamp_utc=parsed.timestamp_utc,
                    timestamp_wita=to_wita(parsed.timestamp_utc),
                    chart_time=to_chart_time(
                        parsed.timestamp_utc,
                        settings.chart_time_offset_hours,
                    ),
                    raw_message=line,
                    source_service=settings.engine_log_source_service,
                )
            )

        return events