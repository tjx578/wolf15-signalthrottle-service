#!/usr/bin/env python3
"""Seed sample SignalThrottle events via webhook for testing."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import httpx


SAMPLE_EVENTS = [
    ("USDJPY", 0),
    ("USDJPY", 5),
    ("USDJPY", 10),
    ("USDJPY", 15),
    ("USDJPY", 20),
    ("USDJPY", 25),
    ("USDJPY", 30),
    ("USDJPY", 60),
    ("USDJPY", 90),
    ("USDJPY", 120),
]


def main():
    parser = argparse.ArgumentParser(description="Seed sample events")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the service",
    )
    parser.add_argument("--secret", default="", help="Webhook secret")
    args = parser.parse_args()

    base_time = datetime.now(timezone.utc) - timedelta(minutes=30)

    for symbol, offset_sec in SAMPLE_EVENTS:
        ts = base_time + timedelta(seconds=offset_sec)
        payload = {
            "event": "signal_throttle",
            "symbol": symbol,
            "timestamp_utc": ts.isoformat(),
            "message": f"[SignalThrottle] {symbol} THROTTLED — 3 signals in last 300s (max 3)",
            "count": 3,
            "window_seconds": 300,
            "max_signals": 3,
            "source_service": "wolf15-engine",
        }
        headers = {"Content-Type": "application/json"}
        if args.secret:
            headers["X-Wolf15-Secret"] = args.secret

        resp = httpx.post(
            f"{args.url}/webhook/log",
            json=payload,
            headers=headers,
            timeout=10,
        )
        print(f"{symbol} +{offset_sec}s: {resp.json()}")


if __name__ == "__main__":
    main()
