# Observer Threat Model

## Protected assets

- Wolf15 strategy and execution authority.
- Canonical telemetry integrity and ordering.
- Observer ledger and replay evidence.
- Owner credentials, incident actions, and exports.
- Railway/PostgreSQL availability.

## Trust boundaries

1. Wolf15 producer to observer ingest.
2. Legacy webhook/log adapters to observer storage; unsafe replay is quarantined.
3. Worker to observer database.
4. Authenticated owner to console.
5. Observer database role to any co-located Wolf15 schema.

## Primary threats and required controls

| Threat | Initial control | Later durable control |
| --- | --- | --- |
| Phase 2 reactivation | Startup reject, route/import/image inventory | Signed release policy and deployment admission |
| Authority leak | Non-executable response fields | Typed allowlist, quarantine, SEV-0 incident |
| Event-ID hash conflict | Legacy hash dedup only | Immutable conflict quarantine |
| Missing/out-of-order data | Coverage unknown | Committed stream sequence, cursor, gap incident |
| Replay changes live state | Production replay route, UI, import, and artifact removed | Namespaced isolated replay and immutable manifest in PR-02 |
| Unauthorized mutation | Default-deny owner auth and server-mapped roles | Durable actor audit and session-grade CSRF for future mutations |
| Raw payload contains secrets | Do not store provider secrets | Pre-persistence redaction and classification |
| Replay/log payload denial of service | Existing request limits are insufficient | Size, rate, concurrency, and backlog limits |
| Stored/reflected XSS | Jinja autoescape | CSP, safe DOM rendering, vendored UI assets |
| Shared-DB resource exhaustion | Separate schema by convention | DB roles, connection quotas, timeouts, workload limits |
| Observer outage affects Wolf15 | No synchronous callback | Cross-system kill and network-failure tests |

## Explicit non-goals of containment PR

- No typed telemetry schema.
- No canonical reconciliation.
- No new database role or migration.
- No Railway rollout.
- No production replay capability; durable isolated replay is deferred to PR-02.
