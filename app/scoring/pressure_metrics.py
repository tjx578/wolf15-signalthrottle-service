from __future__ import annotations

from statistics import mean

from app.models.log_event import LogEvent


def calculate_pressure_metrics(events: list[LogEvent]) -> dict:
    if len(events) < 2:
        return {
            "duration_minutes": 0.0,
            "event_count": len(events),
            "density_per_minute": 0.0,
            "avg_gap_seconds": None,
            "max_gap_seconds": None,
        }

    start = events[0].timestamp_utc
    end = events[-1].timestamp_utc
    duration_seconds = max((end - start).total_seconds(), 1.0)
    gaps = [
        (events[i].timestamp_utc - events[i - 1].timestamp_utc).total_seconds()
        for i in range(1, len(events))
    ]

    duration_minutes = duration_seconds / 60.0

    return {
        "duration_minutes": round(duration_minutes, 2),
        "event_count": len(events),
        "density_per_minute": round(len(events) / duration_minutes, 2),
        "avg_gap_seconds": round(mean(gaps), 2),
        "max_gap_seconds": round(max(gaps), 2),
    }
