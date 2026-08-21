# Wolf15 Observer Authority Boundary

## Runtime mandate

`wolf15-signalthrottle-service` runs permanently as `PHASE1_OBSERVE_ONLY`.
It may ingest, preserve, reconstruct observational pressure blocks, compare
observations with canonical Wolf15 telemetry, and explain evidence to the
owner. It is not a strategy or execution service.

## Authority matrix

| Capability | Wolf15 main | Observer |
| --- | --- | --- |
| Strategy and ContextEpoch | Owns | Mirrors canonical telemetry only |
| PairAdmission decision | Owns | Computes `ExpectedPairAdmissionObservation` only after typed coverage exists |
| Direction and market analysis | Owns | Forbidden |
| Risk and reservation | Owns | Forbidden |
| FinalSignal and command | Owns | Forbidden |
| EA/broker execution | Owns | Forbidden |
| Pressure evidence ledger | Exports telemetry | Owns observer copy |
| Replay S0/S1 | Supplies canonical source | Planned isolated replay; disabled until PR-02 |
| Incidents and owner evidence | Emits canonical facts | Owns observer incidents/read models |

## Production invariants

- `PHASE1_OBSERVE_ONLY=true`.
- `DEPLOYMENT_ENVIRONMENT=production`, `OBSERVER_MODE=observe_only`, and
  `OBSERVER_AUTHORITY=observational_only` remain separate identity fields.
- `ENABLE_MARKET_CONTEXT=false`.
- `ENABLE_TRADE_PLANS=false`.
- `ENABLE_OUTCOME_WORKER=false`.
- `ENABLE_LEGACY_REPLAY=false`; production startup rejects `true`.
- `EXECUTION_ALLOWED=false`.
- `FINNHUB_API_KEY` is absent.
- Owner credentials and a valid owner role are required; absent or partial
  configuration denies owner routes.
- `WEBHOOK_SECRET` is required and separate from owner credentials; an absent
  secret denies ingest.
- GET and HEAD handlers do not rebuild or mutate read models.
- No market, outcome, trade-plan, debug-mutation, EA, broker, risk, command,
  replay-mutation, or execution route is registered.
- Observer shutdown must not change Wolf15 strategy or execution behavior.
- Legacy log input is labelled coverage unknown and never promoted to a
  canonical decision.

## Residual legacy storage

The containment change is intentionally non-destructive. Historical Phase 2
tables and repository methods remain in the source schema until a separately
reviewed data-preservation and migration decision is approved. Production
entrypoints do not call the legacy market/trade-plan/outcome methods, and the
corresponding provider/planner/worker packages are excluded from the Docker
image. This residual is technical debt, not activation authority.

## Upstream blocker

Live typed ingest and canonical reconciliation require an approved
`ObserverTelemetryEnvelopeV1` and committed ordered export stream from Wolf15
main. Until then, coverage is `RAW_COVERAGE_UNKNOWN` and expected admission is
`NOT_EVALUATED`.
