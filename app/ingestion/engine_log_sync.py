from __future__ import annotations

import csv
import io
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx

from ..config import settings
from ..models.log_event import LogEvent
from ..parser.signalthrottle_parser import parse_signalthrottle
from ..parser.timestamp_mapper import to_chart_time, to_wita
from ..storage.repositories import SignalRepository

logger = logging.getLogger(__name__)

_TS_RE = re.compile(r"(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)")
_LAST_SYNC_RESULT: dict[str, Any] = {"status": "never_run"}


@dataclass(frozen=True)
class EngineLogEntry:
    message: str
    timestamp_utc: datetime | None
    severity: str | None = None
    attributes: Any = None
    tags: Any = None
    raw_payload: Any = None
    source_service: str = "wolf15-engine"
    source_path: str = "engine_log_sync"

    @property
    def normalized_payload(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "timestamp": self.timestamp_utc.isoformat() if self.timestamp_utc else None,
            "severity": self.severity,
            "attributes": self.attributes,
            "tags": self.tags,
            "source_service": self.source_service,
            "source_path": self.source_path,
            "raw_payload": self.raw_payload,
        }


def owner_day_window_utc(
    now_utc: datetime,
    owner_timezone: str,
) -> tuple[datetime, datetime]:
    owner_tz = ZoneInfo(owner_timezone)
    localized_now = now_utc.astimezone(owner_tz)
    start_local = datetime.combine(localized_now.date(), time.min, tzinfo=owner_tz)
    return start_local.astimezone(timezone.utc), now_utc.astimezone(timezone.utc)


def utc_day_window_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    normalized_now = _ensure_utc(now_utc)
    start = datetime.combine(normalized_now.date(), time.min, tzinfo=timezone.utc)
    return start, normalized_now


def utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def get_last_sync_result() -> dict[str, Any]:
    return dict(_LAST_SYNC_RESULT)


def set_last_sync_result(result: dict[str, Any]) -> None:
    _LAST_SYNC_RESULT.clear()
    _LAST_SYNC_RESULT.update(result)


def explain_sync_status(last_sync_result: dict[str, Any], today_event_count: int) -> str:
    status = last_sync_result.get("status")
    if today_event_count > 0:
        return "signal_events_exist_today"
    if status == "disabled":
        return "engine_log_sync_disabled"
    if status == "no_source_configured":
        return "engine_log_source_not_configured"
    if status == "no_logs":
        return "engine_log_source_returned_no_logs"
    if status == "error":
        return "engine_log_sync_failed"
    if status == "never_run":
        return "engine_log_sync_not_run_yet"
    return "no_signal_events_found_today"


def parse_engine_log_entries(
    raw_logs: str,
    *,
    source_service: str | None = None,
    source_path: str = "engine_log_sync",
) -> list[EngineLogEntry]:
    if not raw_logs or not raw_logs.strip():
        return []

    service = source_service or settings.engine_log_source_service
    csv_entries = _parse_csv_entries(raw_logs, source_service=service, source_path=source_path)
    if csv_entries is not None:
        return csv_entries

    entries: list[EngineLogEntry] = []
    for raw_line in raw_logs.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        entries.append(_parse_line_entry(line, source_service=service, source_path=source_path))
    return entries


def _parse_csv_entries(
    raw_logs: str,
    *,
    source_service: str,
    source_path: str,
) -> list[EngineLogEntry] | None:
    try:
        reader = csv.DictReader(io.StringIO(raw_logs))
    except csv.Error:
        return None

    fieldnames = {field.lower() for field in (reader.fieldnames or []) if field}
    if "message" not in fieldnames or "timestamp" not in fieldnames:
        return None

    entries: list[EngineLogEntry] = []
    for row in reader:
        message = _first_text(row, "message", "log", "text")
        if not message:
            continue
        timestamp_text = _first_text(row, "timestamp", "timestamp_utc", "time")
        entries.append(
            EngineLogEntry(
                message=message,
                timestamp_utc=_parse_timestamp(timestamp_text),
                severity=_first_text(row, "severity", "level"),
                attributes=_decode_jsonish(row.get("attributes")),
                tags=_decode_jsonish(row.get("tags")),
                raw_payload=dict(row),
                source_service=source_service,
                source_path=source_path,
            )
        )
    return entries


def _parse_line_entry(
    line: str,
    *,
    source_service: str,
    source_path: str,
) -> EngineLogEntry:
    if line.startswith("{"):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            message = _first_text(payload, "message", "log", "text") or line
            timestamp_text = _first_text(
                payload,
                "timestamp",
                "timestamp_utc",
                "time",
                "created_at",
            )
            return EngineLogEntry(
                message=message,
                timestamp_utc=_parse_timestamp(timestamp_text),
                severity=_first_text(payload, "severity", "level"),
                attributes=payload.get("attributes"),
                tags=payload.get("tags"),
                raw_payload=payload,
                source_service=source_service,
                source_path=source_path,
            )

    ts_match = _TS_RE.search(line)
    timestamp_text = ts_match.group("ts") if ts_match else None
    return EngineLogEntry(
        message=line,
        timestamp_utc=_parse_timestamp(timestamp_text),
        raw_payload=line,
        source_service=source_service,
        source_path=source_path,
    )


def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
    lower_lookup = {str(key).lower(): value for key, value in payload.items()}
    for key in keys:
        value = lower_lookup.get(key.lower())
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _decode_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def _parse_timestamp(timestamp_text: str | None) -> datetime | None:
    if not timestamp_text:
        return None

    text = timestamp_text.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    return _ensure_utc(parsed)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
            result = {"status": "disabled"}
            set_last_sync_result(result)
            return result

        if not settings.engine_log_source_url:
            result = {"status": "no_source_configured"}
            set_last_sync_result(result)
            return result

        now_utc = _ensure_utc(self._now_provider())
        start_utc, end_utc = utc_day_window_utc(now_utc)
        overlap_seconds = max(int(settings.engine_log_sync_overlap_seconds or 0), 0)
        fetch_start_utc = start_utc - timedelta(seconds=overlap_seconds)
        raw_logs = await self.fetch_logs(fetch_start_utc, end_utc)
        if not raw_logs.strip():
            result = {
                "status": "no_logs",
                "start_utc": start_utc.isoformat(),
                "fetch_start_utc": fetch_start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
            }
            set_last_sync_result(result)
            return result

        result = await self.ingest_logs(raw_logs, source_path="engine_log_sync")
        result.update(
            {
                "status": "ok",
                "start_utc": start_utc.isoformat(),
                "fetch_start_utc": fetch_start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
            }
        )
        set_last_sync_result(result)
        return result

    async def fetch_logs(self, start_utc: datetime, end_utc: datetime) -> str:
        headers: dict[str, str] = {}
        if settings.engine_log_source_token:
            headers["Authorization"] = f"Bearer {settings.engine_log_source_token}"

        params = {
            "start_utc": _ensure_utc(start_utc).isoformat().replace("+00:00", "Z"),
            "end_utc": _ensure_utc(end_utc).isoformat().replace("+00:00", "Z"),
        }
        if settings.engine_log_fetch_filter:
            params["contains"] = settings.engine_log_fetch_filter

        async with httpx.AsyncClient(timeout=settings.engine_log_sync_timeout_seconds) as client:
            response = await client.get(
                settings.engine_log_source_url,
                params=params,
                headers=headers,
            )
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return self._payload_to_log_text(response.json())

        return response.text

    async def ingest_logs(
        self,
        raw_logs: str,
        *,
        source_path: str = "engine_log_sync",
    ) -> dict[str, Any]:
        repo = self._repo_factory()
        stored = 0
        duplicates = 0
        parsed_count = 0
        raw_stored = 0
        raw_duplicates = 0
        signalthrottle_invalid = 0
        non_signalthrottle = 0

        entries = parse_engine_log_entries(
            raw_logs,
            source_service=settings.engine_log_source_service,
            source_path=source_path,
        )
        entries = sorted(
            entries,
            key=lambda entry: entry.timestamp_utc or datetime.max.replace(tzinfo=timezone.utc),
        )

        for entry in entries:
            parsed = (
                parse_signalthrottle(raw_message=entry.message, timestamp_utc=entry.timestamp_utc)
                if entry.timestamp_utc is not None
                else None
            )
            message_mentions_signalthrottle = "SignalThrottle" in entry.message
            parse_status = _entry_parse_status(
                has_timestamp=entry.timestamp_utc is not None,
                mentions_signalthrottle=message_mentions_signalthrottle,
                parsed=parsed is not None,
            )

            engine_log_entry_id: int | None = None
            if hasattr(repo, "insert_engine_log_entry"):
                raw_result = await repo.insert_engine_log_entry(
                    timestamp_utc=entry.timestamp_utc,
                    message=entry.message,
                    severity=entry.severity,
                    attributes=entry.attributes,
                    tags=entry.tags,
                    source_service=entry.source_service,
                    source_path=entry.source_path,
                    is_signalthrottle=parsed is not None,
                    parse_status=parse_status,
                    symbol=parsed.symbol if parsed else None,
                    signal_count=parsed.count if parsed else None,
                    window_seconds=parsed.window_seconds if parsed else None,
                    max_signals=parsed.max_signals if parsed else None,
                    raw_payload=entry.normalized_payload,
                )
                engine_log_entry_id = raw_result.get("id")
                if raw_result.get("duplicate"):
                    raw_duplicates += 1
                else:
                    raw_stored += 1

            if parsed is None:
                if message_mentions_signalthrottle:
                    signalthrottle_invalid += 1
                else:
                    non_signalthrottle += 1
                continue

            parsed_count += 1
            result = await repo.insert_signal_event(
                symbol=parsed.symbol,
                event_type="SIGNAL_THROTTLE",
                timestamp_utc=parsed.timestamp_utc,
                raw_message=entry.message,
                source_service=entry.source_service,
                timestamp_wita=to_wita(parsed.timestamp_utc),
                chart_time=to_chart_time(
                    parsed.timestamp_utc,
                    settings.chart_time_offset_hours,
                ),
                meta={
                    "sync_source": source_path,
                    "source_path": source_path,
                    "engine_log_entry_id": engine_log_entry_id,
                    "signal_count": parsed.count,
                    "window_seconds": parsed.window_seconds,
                    "max_signals": parsed.max_signals,
                },
            )
            if result.get("duplicate"):
                duplicates += 1
                continue

            stored += 1
            await repo.upsert_live_block_from_event(
                LogEvent(
                    symbol=parsed.symbol,
                    event_type="SIGNAL_THROTTLE",
                    timestamp_utc=parsed.timestamp_utc,
                    timestamp_wita=to_wita(parsed.timestamp_utc),
                    chart_time=to_chart_time(
                        parsed.timestamp_utc,
                        settings.chart_time_offset_hours,
                    ),
                    raw_message=entry.message,
                    source_service=entry.source_service,
                ),
                max_event_gap_seconds=settings.max_event_gap_seconds,
                chart_offset_hours=settings.chart_time_offset_hours,
            )

        return {
            "raw_logs_seen": len(entries),
            "raw_logs_stored": raw_stored,
            "raw_duplicates_skipped": raw_duplicates,
            "events_parsed": parsed_count,
            "events_stored": stored,
            "duplicates_skipped": duplicates,
            "signalthrottle_invalid": signalthrottle_invalid,
            "non_signalthrottle_logs": non_signalthrottle,
        }

    def _parse_events(self, raw_logs: str) -> list[LogEvent]:
        events: list[LogEvent] = []
        for entry in parse_engine_log_entries(raw_logs):
            if entry.timestamp_utc is None:
                continue
            parsed = parse_signalthrottle(raw_message=entry.message, timestamp_utc=entry.timestamp_utc)
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
                    raw_message=entry.message,
                    source_service=entry.source_service,
                )
            )
        return events

    def _payload_to_log_text(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, list):
            return "\n".join(self._serialize_log_item(item) for item in payload if item is not None)
        if isinstance(payload, dict):
            for key in ("logs", "lines", "entries", "data", "results", "items"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value
                if isinstance(value, list):
                    return "\n".join(self._serialize_log_item(item) for item in value if item is not None)
            return self._serialize_log_item(payload)
        return ""

    def _serialize_log_item(self, item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            return json.dumps(item, ensure_ascii=False)
        return str(item)


def _entry_parse_status(
    *,
    has_timestamp: bool,
    mentions_signalthrottle: bool,
    parsed: bool,
) -> str:
    if parsed:
        return "SIGNALTHROTTLE_VALID"
    if mentions_signalthrottle and not has_timestamp:
        return "SIGNALTHROTTLE_MISSING_TIMESTAMP"
    if mentions_signalthrottle:
        return "SIGNALTHROTTLE_PARSE_FAILED"
    return "NON_SIGNALTHROTTLE"
