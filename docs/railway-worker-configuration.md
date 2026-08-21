# Legacy Railway replay worker — retired

> **LEGACY_UNSAFE_REPLAY — NOT FOR PRODUCTION**

The former `test-replay-logs` Railway worker procedure is retired. Do not
configure, start, or restore that worker.

PR-01 deliberately enforces all of the following:

- `POST /replay/logs` is not registered and returns `404`.
- The dashboard contains no replay input or submit control.
- `app/api/routes_replay.py` and `scripts/` are excluded from the production
  Docker image.
- `ENABLE_LEGACY_REPLAY=true` is rejected at production startup.

Replay may return only through the PR-02 durable isolated replay contract,
including an immutable manifest, durable idempotency, an isolated namespace
and cursor, immutable output hashes, and explicit abuse limits.

This file remains solely as a tombstone so historical links cannot be mistaken
for active operational guidance.
