"""Test /replay/logs endpoint with sample USDJPY B+ pressure logs."""
import asyncio
import httpx
from datetime import datetime

__test__ = False

URL = "https://wolf15-signalthrottle-service-production.up.railway.app"

# Sample USDJPY B+ pressure logs (70 lines, 5.75 minutes)
LOGS = """2026-04-27T02:00:05Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:00:10Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:00:15Z [SignalThrottle] USDJPY THROTTLED — 4 signals in last 10s
2026-04-27T02:00:20Z [SignalThrottle] USDJPY THROTTLED — 7 signals in last 10s
2026-04-27T02:00:25Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:00:30Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:00:35Z [SignalThrottle] USDJPY THROTTLED — 3 signals in last 10s
2026-04-27T02:00:40Z [SignalThrottle] USDJPY THROTTLED — 8 signals in last 10s
2026-04-27T02:00:45Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:00:50Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:00:55Z [SignalThrottle] USDJPY THROTTLED — 4 signals in last 10s
2026-04-27T02:01:00Z [SignalThrottle] USDJPY THROTTLED — 7 signals in last 10s
2026-04-27T02:01:05Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:01:10Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:01:15Z [SignalThrottle] USDJPY THROTTLED — 3 signals in last 10s
2026-04-27T02:01:20Z [SignalThrottle] USDJPY THROTTLED — 8 signals in last 10s
2026-04-27T02:01:25Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:01:30Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:01:35Z [SignalThrottle] USDJPY THROTTLED — 4 signals in last 10s
2026-04-27T02:01:40Z [SignalThrottle] USDJPY THROTTLED — 7 signals in last 10s
2026-04-27T02:01:45Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:01:50Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:01:55Z [SignalThrottle] USDJPY THROTTLED — 3 signals in last 10s
2026-04-27T02:02:00Z [SignalThrottle] USDJPY THROTTLED — 8 signals in last 10s
2026-04-27T02:02:05Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:02:10Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:02:15Z [SignalThrottle] USDJPY THROTTLED — 4 signals in last 10s
2026-04-27T02:02:20Z [SignalThrottle] USDJPY THROTTLED — 7 signals in last 10s
2026-04-27T02:02:25Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:02:30Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:02:35Z [SignalThrottle] USDJPY THROTTLED — 3 signals in last 10s
2026-04-27T02:02:40Z [SignalThrottle] USDJPY THROTTLED — 8 signals in last 10s
2026-04-27T02:02:45Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:02:50Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:02:55Z [SignalThrottle] USDJPY THROTTLED — 4 signals in last 10s
2026-04-27T02:03:00Z [SignalThrottle] USDJPY THROTTLED — 7 signals in last 10s
2026-04-27T02:03:05Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:03:10Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:03:15Z [SignalThrottle] USDJPY THROTTLED — 3 signals in last 10s
2026-04-27T02:03:20Z [SignalThrottle] USDJPY THROTTLED — 8 signals in last 10s
2026-04-27T02:03:25Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:03:30Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:03:35Z [SignalThrottle] USDJPY THROTTLED — 4 signals in last 10s
2026-04-27T02:03:40Z [SignalThrottle] USDJPY THROTTLED — 7 signals in last 10s
2026-04-27T02:03:45Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:03:50Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:03:55Z [SignalThrottle] USDJPY THROTTLED — 3 signals in last 10s
2026-04-27T02:04:00Z [SignalThrottle] USDJPY THROTTLED — 8 signals in last 10s
2026-04-27T02:04:05Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:04:10Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:04:15Z [SignalThrottle] USDJPY THROTTLED — 4 signals in last 10s
2026-04-27T02:04:20Z [SignalThrottle] USDJPY THROTTLED — 7 signals in last 10s
2026-04-27T02:04:25Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:04:30Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:04:35Z [SignalThrottle] USDJPY THROTTLED — 3 signals in last 10s
2026-04-27T02:04:40Z [SignalThrottle] USDJPY THROTTLED — 8 signals in last 10s
2026-04-27T02:04:45Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:04:50Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:04:55Z [SignalThrottle] USDJPY THROTTLED — 4 signals in last 10s
2026-04-27T02:05:00Z [SignalThrottle] USDJPY THROTTLED — 7 signals in last 10s
2026-04-27T02:05:05Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:05:10Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:05:15Z [SignalThrottle] USDJPY THROTTLED — 3 signals in last 10s
2026-04-27T02:05:20Z [SignalThrottle] USDJPY THROTTLED — 8 signals in last 10s
2026-04-27T02:05:25Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:05:30Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s
2026-04-27T02:05:35Z [SignalThrottle] USDJPY THROTTLED — 4 signals in last 10s
2026-04-27T02:05:40Z [SignalThrottle] USDJPY THROTTLED — 7 signals in last 10s
2026-04-27T02:05:45Z [SignalThrottle] USDJPY THROTTLED — 5 signals in last 10s
2026-04-27T02:05:50Z [SignalThrottle] USDJPY THROTTLED — 6 signals in last 10s"""


async def test_replay_endpoint():
    """Test the replay endpoint with sample logs."""
    print("🧪 Testing POST /replay/logs endpoint\n")
    print(f"URL: {URL}")
    print(f"Logs: 70 lines, USDJPY B+ pressure\n")

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            # Step 1: Health check
            print("1️⃣ Checking /health...")
            health = await client.get(f"{URL}/health")
            print(f"   Status: {health.status_code}")

            # Step 2: Market snapshot
            print("\n2️⃣ Checking /market/snapshot/USDJPY...")
            market = await client.get(f"{URL}/market/snapshot/USDJPY")
            print(f"   Status: {market.status_code}")
            if market.status_code == 200:
                market_data = market.json()
                counts = market_data.get("counts", {})
                print(
                    f"   Candles: M15={counts.get('M15')}, H1={counts.get('H1')}, "
                    f"H4={counts.get('H4')}, D1={counts.get('D1')}"
                )

            # Step 3: Replay logs
            print("\n3️⃣ Posting /replay/logs...")
            replay = await client.post(f"{URL}/replay/logs", json={"logs": LOGS})
            print(f"   Status: {replay.status_code}")
            if replay.status_code == 200:
                replay_data = replay.json()
                print(f"   Response:")
                print(f"     - Status: {replay_data.get('status')}")
                print(f"     - Events parsed: {replay_data.get('events_parsed')}")
                print(f"     - Events stored: {replay_data.get('events_stored')}")
                print(f"     - Canonical blocks detected: {replay_data.get('canonical_blocks_detected')}")
                print(f"     - Trade plans created: {replay_data.get('trade_plans_created')}")
                if replay_data.get("blocks"):
                    block = replay_data["blocks"][0]
                    print(f"   Block details:")
                    print(f"     - Symbol: {block.get('symbol')}")
                    print(f"     - Pressure grade: {block.get('pressure_grade')}")
                    print(f"     - Duration: {block.get('duration_minutes'):.2f} min")
                    print(f"     - Event count: {block.get('event_count')}")
            else:
                print(f"   Error: {replay.text}")

            # Step 4: Get signals
            print("\n4️⃣ Checking /signals/latest...")
            signals = await client.get(f"{URL}/signals/latest")
            print(f"   Status: {signals.status_code}")
            if signals.status_code == 200:
                signals_data = signals.json()
                print(f"   Count: {signals_data.get('count')}")
                if signals_data.get("signals"):
                    latest = signals_data["signals"][0]
                    print(f"   Latest signal: {latest.get('symbol')} ({latest.get('pressure_grade')})")

            print("\n✅ Replay test completed!")

        except Exception as error:
            print(f"\n❌ Error: {error}")
            return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(test_replay_endpoint())
    exit(exit_code)
