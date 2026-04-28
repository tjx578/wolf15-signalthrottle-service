#!/usr/bin/env python3
"""
CLI script to replay raw signal throttle logs via the /replay/logs endpoint.

This script is designed to be used as a Railway worker to test replay functionality.

Usage:
    python scripts/replay_logs.py <log_file> --url <service_url> [--auth USER:PASS]

Example (Railway worker start command):
    python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log \\
        --url $SIGNAL_THROTTLE_URL && sleep 3600
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import httpx


def _format_json(data: dict) -> str:
    """Pretty-print JSON."""
    return json.dumps(data, indent=2, default=str)


def main() -> int:
    """Run the replay test."""
    parser = argparse.ArgumentParser(
        description="Replay SignalThrottle logs to service",
        epilog="""
Examples:
  python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log \\
    --url https://wolf15-signalthrottle-service-production.up.railway.app

  python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log \\
    --url http://localhost:8000 --auth admin:password
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file", type=Path, help="Path to log file")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the service (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--auth",
        help="Basic auth credentials (format: username:password)",
    )
    parser.add_argument(
        "--symbol",
        default="USDJPY",
        help="Symbol to check in /market/snapshot (default: USDJPY)",
    )
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip health check",
    )
    parser.add_argument(
        "--skip-market",
        action="store_true",
        help="Skip market snapshot check",
    )
    parser.add_argument(
        "--skip-signals",
        action="store_true",
        help="Skip signals check after replay",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60,
        help="HTTP timeout in seconds (default: 60)",
    )
    args = parser.parse_args()

    # Validate log file
    if not args.file.exists():
        print(f"❌ Log file not found: {args.file}")
        return 1

    try:
        logs = args.file.read_text(encoding="utf-8")
    except Exception as e:
        print(f"❌ Failed to read log file: {e}")
        return 1

    print(f"📄 Loaded {len(logs.splitlines())} lines from {args.file}")
    print(f"🎯 Service URL: {args.url}\n")

    # Setup auth headers
    headers = {}
    if args.auth:
        try:
            username, password = args.auth.split(":", 1)
            auth_str = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_str}"
            print(f"🔐 Using basic auth for user: {username}\n")
        except ValueError:
            print("❌ Invalid auth format. Use: username:password")
            return 1

    base_url = args.url.rstrip("/")

    try:
        with httpx.Client(timeout=args.timeout) as client:
            # Step 1: Health check
            if not args.skip_health:
                print("1️⃣ Health check...")
                try:
                    health = client.get(f"{base_url}/health")
                    if health.status_code != 200:
                        print(f"   ❌ Failed: {health.status_code}")
                        print(f"   {health.text[:200]}")
                        return 1
                    print("   ✅ Service is healthy\n")
                except httpx.ConnectError:
                    print("   ❌ Connection error - is service running?")
                    return 1

            # Step 2: Market snapshot
            if not args.skip_market:
                print(f"2️⃣ Market snapshot for {args.symbol}...")
                try:
                    market = client.get(f"{base_url}/market/snapshot/{args.symbol}")
                    if market.status_code != 200:
                        print(f"   ❌ Failed: {market.status_code}")
                    else:
                        data = market.json()
                        counts = data.get("counts", {})
                        print(
                            f"   ✅ M15={counts.get('M15')}, "
                            f"H1={counts.get('H1')}, "
                            f"H4={counts.get('H4')}, "
                            f"D1={counts.get('D1')} candles\n"
                        )
                except Exception as e:
                    print(f"   ⚠️  Market check failed: {e}\n")

            # Step 3: Replay logs
            print("3️⃣ Replaying logs...")
            try:
                replay = client.post(
                    f"{base_url}/replay/logs",
                    json={"logs": logs},
                    headers=headers,
                )

                if replay.status_code not in (200, 401):
                    print(f"   ❌ Failed: {replay.status_code}")
                    print(f"   {replay.text[:300]}")
                    return 1

                if replay.status_code == 401:
                    print("   ⚠️  Authentication required (401)")
                    print("      Use --auth username:password")
                    return 1

                data = replay.json()

                # Check for errors
                if data.get("status") == "error":
                    print(f"   ❌ Replay error: {data.get('error')}")
                    print(f"      {data.get('message')}")
                    return 1

                print("   ✅ Replay successful\n")
                print("📊 Results:")
                print(f"   - Events parsed: {data.get('events_parsed')}")
                print(f"   - Events stored: {data.get('events_stored')}")
                print(f"   - Duplicates: {data.get('duplicates_skipped')}")
                print(f"   - Blocks detected: {data.get('canonical_blocks_detected')}")
                print(f"   - Blocks created: {data.get('blocks_created')}")
                print(f"   - Blocks updated: {data.get('blocks_updated')}")
                print(f"   - Trade plans: {data.get('trade_plans_created')}\n")

                # Show block details
                blocks = data.get("blocks", [])
                if blocks:
                    print("🔗 Blocks:")
                    for i, block in enumerate(blocks, 1):
                        print(f"   [{i}] {block.get('symbol')}")
                        print(f"       Grade: {block.get('pressure_grade')}")
                        print(f"       Duration: {block.get('duration_minutes'):.2f} min")
                        print(f"       Events: {block.get('event_count')}")
                        print(f"       Density: {block.get('density_per_minute'):.2f}/min")
                        print(f"       Trade plan: {block.get('trade_plan_created')}\n")

            except httpx.RequestError as e:
                print(f"   ❌ Request failed: {e}")
                return 1

            # Step 4: Check signals
            if not args.skip_signals:
                print("4️⃣ Checking latest signals...")
                try:
                    signals = client.get(f"{base_url}/signals/latest?limit=5")
                    if signals.status_code == 200:
                        data = signals.json()
                        count = data.get("count", 0)
                        print(f"   ✅ Found {count} signals")
                        if data.get("signals"):
                            latest = data["signals"][0]
                            print(f"      Latest: {latest.get('symbol')} ({latest.get('pressure_grade')})\n")
                    else:
                        print(f"   ⚠️  Status {signals.status_code}\n")
                except Exception as e:
                    print(f"   ⚠️  Failed: {e}\n")

        print("✅ Replay test completed successfully!")
        return 0

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
