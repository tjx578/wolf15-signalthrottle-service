#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import httpx


def _parse_fixture_line(line: str) -> tuple[str, str, str]:
    timestamp, message = line.split(" ", 1)
    parts = message.split()
    symbol = parts[1] if len(parts) > 1 else "UNKNOWN"
    return timestamp, symbol, message


async def main() -> int:
    parser = argparse.ArgumentParser(description="Send a replay fixture through /webhook/log")
    parser.add_argument("fixture", help="Path to fixture log file")
    parser.add_argument("--url", required=True, help="Base URL of the service")
    parser.add_argument("--secret", required=True, help="Webhook secret header value")
    parser.add_argument("--source", default="fixture-webhook", help="Source service name")
    parser.add_argument("--pipeline-version", default="phase3-test", help="Pipeline version")
    parser.add_argument("--timeout", type=float, default=20, help="HTTP timeout in seconds")
    args = parser.parse_args()

    lines = [
        line.strip()
        for line in Path(args.fixture).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    async with httpx.AsyncClient(timeout=args.timeout) as client:
        for line in lines:
            timestamp, symbol, message = _parse_fixture_line(line)
            payload = {
                "event": "signal_throttle",
                "symbol": symbol,
                "timestamp_utc": timestamp,
                "message": message,
                "count": 3,
                "window_seconds": 300,
                "max_signals": 3,
                "source_service": args.source,
                "pipeline_version": args.pipeline_version,
            }
            response = await client.post(
                f"{args.url.rstrip('/')}/webhook/log",
                json=payload,
                headers={"X-Wolf15-Secret": args.secret},
            )
            try:
                body = response.json()
            except ValueError:
                body = response.text
            print(f"[{response.status_code}] {json.dumps(body, default=str)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))