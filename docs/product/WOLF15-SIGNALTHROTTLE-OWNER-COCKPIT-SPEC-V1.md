---
document_id: WOLF15-SIGNALTHROTTLE-OWNER-COCKPIT-SPEC-V1
document_status: PROPOSED_IMPLEMENTATION_SPEC
deployment_environment: PRODUCTION
observer_mode: OBSERVE_ONLY
observer_authority: OBSERVATIONAL_ONLY
strategy_authority: NONE
execution_authority: NONE
baseline_repo_commit: 610d6ebcf548c44488ddeecd33671a7315357ab8
supersedes: null
depends_on:
  - Wolf15 Observer Architecture
  - Wolf15 Strategy SSOT V3.1
  - Wolf15 Audit Replay Workflow V3
---

# Wolf15 SignalThrottle Owner Cockpit V1

## Status and scope

This document is the corrected product and implementation contract for the
owner cockpit. It is not a strategy SSOT and grants this repository no
strategy, risk, command, broker, or execution authority.

V1 may present observational evidence, integrity status, incidents, and
canonical facts exported by Wolf15. Durable replay evidence is deferred to
PR-02. It may never infer missing
canonical strategy facts from log order or implement H4/H1/M15 analysis,
DirectionalThesis, TradePlan, risk reservation, FinalSignal, or
ExecutionCommand.

## Runtime identity

The three identity dimensions are independent:

```yaml
deployment_environment: PRODUCTION
observer_mode: OBSERVE_ONLY
observer_authority: OBSERVATIONAL_ONLY
```

`PRODUCTION` describes deployment, not execution. `OBSERVATIONAL_ONLY` is an
authority classification, not a health claim. A verified containment label may
only be shown when runtime, credential, database-grant, egress, and emitted
object invariants have actually been measured. Otherwise its verification
state is `UNKNOWN`.

## Authority-carrying field contract

Every canonical or derived cockpit field must carry provenance:

```yaml
value: unknown
source_authority: LEGACY_OBSERVATIONAL | OBSERVER_DERIVED | CANONICAL_WOLF15
source_event_type: string | null
source_event_id: string | null
source_commit: string | null
rule_version: string | null
observed_at_utc: timestamp
freshness: FRESH | STALE | UNKNOWN
coverage_status: COMPLETE | INCOMPLETE | UNKNOWN | NOT_APPLICABLE
```

`source_emission_stage` and `canonical_analysis_stage` are separate fields.
When Wolf15 does not export a canonical stage, `canonical_analysis_stage` is
`UNKNOWN`.

## Canonical admission enum

The ambiguous value `N.A.` is forbidden. Pair admission uses:

```text
EVALUATED_GRANTED
EVALUATED_REJECTED
EVALUATED_SUSPENDED
NOT_APPLICABLE_NO_RAW_AUTHORITY_BLOCK
MISSING_EVALUATION_INCIDENT
INDETERMINATE_RAW_AUTHORITY_COVERAGE
UNKNOWN
```

Legacy input remains `LEGACY_OBSERVATIONAL`. When raw authority coverage is not
complete, expected admission is `NOT_EVALUATED`.

## Owner snapshot consistency

Future `OwnerSystemSnapshot` objects are immutable and include:

```yaml
snapshot_id: uuid
created_at_utc: timestamp
as_of_utc: timestamp
source_watermark: string
observer_commit: string
wolf15_commit: string | null
schema_versions: object
policy_versions: object
read_model_versions: object
canonical_feed_status: object
raw_coverage_status: object
authority_status: object
```

They must be produced either within one PostgreSQL `REPEATABLE READ`
transaction or as one atomically published materialized snapshot row. A page
must not claim snapshot consistency while mixing independent watermarks.

## Read and mutation safety

- HTTP GET and HEAD are side-effect free.
- Owner access is default-deny. Missing auth configuration is not anonymous
  mode.
- Machine ingest is default-deny and uses a credential separate from owner UI.
- Browser mutations require actor identity, request ID, audit record, reason,
  and CSRF protection. Relevant operations also require an idempotency key.
- Phase 2 outcome/trade-plan backfill is forbidden. A future permitted backfill
  is named `telemetry backfill` and remains bounded and audited.

The minimum default-deny role model is:

| Role | Current authority |
| --- | --- |
| `OWNER_VIEWER` | Authenticated owner reads only |
| `OWNER_OPERATOR` | Viewer rights; reserved for future bounded operations |
| `OWNER_ADMIN` | Operator rights; future maintenance/settings gates |
| `SERVICE_INGEST` | Machine telemetry ingest only; never owner UI access |

## Replay capability status

```text
LEGACY_UNSAFE_REPLAY = DISABLED
PRODUCTION_ROUTE = ABSENT
PRODUCTION_UI_CONTROL = ABSENT
PRODUCTION_ARTIFACT = ABSENT
DURABLE_ISOLATED_REPLAY = HOLD_PR02
```

The quarantined legacy module is not a supported production capability. PR-02
must introduce an immutable replay manifest, durable request idempotency,
isolated namespace and cursor, and immutable output hashes before any replay
route can return to production.

## Health contract

- `/health/live` reports process liveness and immutable containment identity.
- `/health/ready` checks required auth configuration, ingest authentication,
  database connectivity, observer schema status, and containment invariants.
- Unavailable checks are `UNKNOWN`, never synthetic success or zero.
- Canonical feed checks remain `HOLD_UPSTREAM` until typed export exists.

## Incident semantics

An executable observer-derived object is an authority leak and SEV-0 when:

```text
source_authority in {
  RAW_SIGNALTHROTTLE,
  DERIVED_PRESSURE_ADVISORY,
  OBSERVER_DERIVED
}
AND valid_for_execution = true
```

A read-only canonical Wolf15 mirror may retain its canonical executable status
for audit, but the observer may not produce, modify, sign, or forward it.

## Upstream dependency and hold line

Full Why No Trade, canonical PairAdmission reconciliation, canonical lifecycle,
risk/final/command counters, and semantic deployment comparison are `HOLD`
until Wolf15 publishes a versioned typed export with authority, ordering,
watermark, commit, and policy metadata.

Until then the UI may expose only legacy observational Pair Radar, labelled as
such, and must use `UNKNOWN` rather than inventing canonical facts.

## V1 implementation order

1. Baseline and authority inventory.
2. Dashboard safety patch: containment, auth and webhook fail-closed, GET
   read-only, and real live/ready health.
3. Durable pool, atomic reducer, cursor, migrations, and lifecycle FSM.
4. Typed Wolf15 export track.
5. Consistent OwnerSystemSnapshot and materialized read models.
6. Cockpit views, incidents, evidence, and deployment intelligence.
7. Durable isolated replay after its PR-02 safety contract is satisfied.
