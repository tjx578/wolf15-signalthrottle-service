#!/usr/bin/env python3
"""CLI script to replay raw logs via the /replay/logs endpoint."""
from __future__ import annotations

import argparse
import json
import sys

import httpx


def _print_response(label: str, response: httpx.Response) -> None:
    print(f"[{label}] {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2))
    except ValueError:
        print(response.text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay SignalThrottle logs")
    parser.add_argument("file", help="Path to log file")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the service",
    )
    parser.add_argument(
        "--symbol",
        default="USDJPY",
        help="Symbol to use for /market/snapshot check",
    )
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip GET /health before replaying logs",
    )
    parser.add_argument(
        "--skip-market",
        action="store_true",
        help="Skip GET /market/snapshot/{symbol} before replaying logs",
    )
    parser.add_argument(
        "--skip-signals",
        action="store_true",
        help="Skip GET /signals/latest after replaying logs",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Limit for GET /signals/latest",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60,
        help="HTTP timeout in seconds",
    )
    args = parser.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        logs = f.read()

    base_url = args.url.rstrip("/")

    with httpx.Client(timeout=args.timeout) as client:
        if not args.skip_health:
            health = client.get(f"{base_url}/health")
            _print_response("health", health)
            health.raise_for_status()

        if not args.skip_market:
            market = client.get(f"{base_url}/market/snapshot/{args.symbol}")
            _print_response("market", market)
            market.raise_for_status()

        replay = client.post(
            f"{base_url}/replay/logs",
            json={"logs": logs},
        )
        _print_response("replay", replay)
        replay.raise_for_status()

        if not args.skip_signals:
            signals = client.get(f"{base_url}/signals/latest", params={"limit": args.limit})
            _print_response("signals", signals)
            signals.raise_for_status()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
