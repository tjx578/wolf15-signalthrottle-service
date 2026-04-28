# Railway Worker Configuration: `test-replay-logs`

## Problem

The original worker configuration tried to run a JavaScript test script with Bun via stdin:

```bash
bun run [stdin]  # ❌ WRONG - [stdin] is not a file
```

This caused:

```text
error: Module not found '/app/[stdin]'
```

## Solution

Use a proper Python script as the start command instead of Bun stdin.

## Configuration Steps

### 1. Set Start Command

In Railway dashboard → service `test-replay-logs` → Settings → Start Command:

```bash
python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log --url $SIGNAL_THROTTLE_URL
```

Or with authentication:

```bash
python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log --url $SIGNAL_THROTTLE_URL --auth $WEBHOOK_USER:$WEBHOOK_PASS
```

### 2. Set Environment Variables

In Railway dashboard → service `test-replay-logs` → Variables:

```env
SIGNAL_THROTTLE_URL=https://wolf15-signalthrottle-service-production.up.railway.app
WEBHOOK_USER=dashboard_user
WEBHOOK_PASS=secure_password_here
```

### 3. Optional: Make Worker Loop (if needed)

If Railway expects the worker to stay alive (not exit immediately):

```bash
python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log --url $SIGNAL_THROTTLE_URL && sleep 3600
```

Or to run repeatedly every 5 minutes:

```bash
while true; do
  python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log --url $SIGNAL_THROTTLE_URL
  sleep 300
done
```

## Script Usage

### Basic replay (no auth)

```bash
python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log \
  --url https://wolf15-signalthrottle-service-production.up.railway.app
```

### With basic auth

```bash
python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log \
  --url https://my-service.up.railway.app \
  --auth admin:password123
```

### Local development

```bash
python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log \
  --url http://localhost:8000
```

### Skip certain checks

```bash
python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log \
  --url http://localhost:8000 \
  --skip-health \
  --skip-market
```

## What the Script Does

1. **Health Check** - Verifies service is running (`/health`)
2. **Market Snapshot** - Checks OHLC data availability (`/market/snapshot/USDJPY`)
3. **Replay Logs** - Sends logs to `/replay/logs` endpoint
4. **Verify Signals** - Checks that signals were created (`/signals/latest`)

## Error Handling

The script:

- ✅ Handles connection errors gracefully
- ✅ Detects authentication failures (401)
- ✅ Reports API errors with context
- ✅ Validates log file exists before attempting upload
- ✅ Exits with code 0 on success, 1 on failure

## Why Not Bun?

Since `wolf15-signalthrottle-service` is a **Python project** (FastAPI), the test worker should also be Python:

| Approach | ✓ Pros | ✗ Cons |
| --- | --- | --- |
| **Python script** | Native to project, no extra runtime, easy debugging | Requires Python |
| **Bun TypeScript** | Fast, modern JS/TS | Adds complexity, extra runtime, stdin issues |
| **Bash script** | Simple, portable | Limited error handling |

**Recommendation**: Use Python script for workers in Python projects.

## Testing Locally

```bash
# Test with production service
python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log \
  --url https://wolf15-signalthrottle-service-production.up.railway.app

# Test with local service (dev)
python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log \
  --url http://localhost:8000
```

## Monitoring

Check worker logs in Railway dashboard:

- Successful: `✅ Replay test completed successfully!`
- Auth failure: `⚠️ Authentication required (401)`
- Connection error: `❌ Connection error - is service running?`
- Service error: Shows error code and message from API

## Next Steps

1. Update worker start command to use Python script
2. Set `SIGNAL_THROTTLE_URL` environment variable
3. (Optional) Set auth credentials if endpoint requires it
4. Deploy and check logs

---

**Result**: Clean, maintainable test worker with proper error handling and no stdin issues! 🚀
