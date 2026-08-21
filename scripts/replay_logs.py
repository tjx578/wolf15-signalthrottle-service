#!/usr/bin/env python3
"""LEGACY_UNSAFE_REPLAY — NOT_FOR_PRODUCTION.

Historical CLI for the removed ``/replay/logs`` endpoint. The production image
excludes ``scripts/`` and the endpoint is intentionally not registered. Keep
this file only as research input for the PR-02 durable isolated replay design.

Usage:
    python scripts/replay_logs.py <log_file> --url <service_url> [--auth USER:PASS]

Historical local example (the request now returns 404):
    python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log \\
        --url $SIGNAL_THROTTLE_URL && sleep 3600
"""
from __future__ import annotations

import argparse
import base64
import json
import uuid
from pathlib import Path

import httpx


def _format_json(data: dict) -> str:
    """Pretty-print JSON."""
    return json.dumps(data, indent=2, default=str)


def main() -> int:
    """Run the replay test."""
    parser = argparse.ArgumentParser(
        description="LEGACY_UNSAFE_REPLAY research CLI (production endpoint removed)",
        epilog="""
Examples:
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
        "--skip-health",
        action="store_true",
        help="Skip health check",
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
    headers = {
        "X-Owner-CSRF": "1",
        "X-Owner-Request-ID": f"replay-cli-{uuid.uuid4()}",
        "X-Owner-Reason": "manual_observational_replay",
    }
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

            # Step 2: Replay logs
            print("2️⃣ Replaying logs...")
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
                print(f"   - Observational blocks: {data.get('observational_blocks_detected')}")
                print(f"   - Blocks created: {data.get('blocks_created')}")
                print(f"   - Blocks updated: {data.get('blocks_updated')}\n")

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
                        print("       Execution allowed: false\n")

            except httpx.RequestError as e:
                print(f"   ❌ Request failed: {e}")
                return 1

            # Step 3: Check observations
            if not args.skip_signals:
                print("3️⃣ Checking latest observations...")
                try:
                    signals = client.get(
                        f"{base_url}/signals/latest?limit=5",
                        headers=headers,
                    )
                    if signals.status_code == 200:
                        data = signals.json()
                        count = data.get("count", 0)
                        print(f"   ✅ Found {count} observations")
                        if data.get("observations"):
                            latest = data["observations"][0]
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
