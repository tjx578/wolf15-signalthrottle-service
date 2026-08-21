# Repository Baseline — 610d6eb

Baseline commit:
`610d6ebcf548c44488ddeecd33671a7315357ab8` on `main`.

## Pre-containment runtime inventory

- FastAPI routes: dashboard, debug migrations/schema/sync, webhook, replay,
  signals, blocks, market snapshot, and outcomes/backfill.
- Workers: pressure finalizer, optional outcome worker, optional full-day
  Railway log synchronization.
- Outbound dependencies: configured engine-log source and Finnhub.
- Activation variables: `SIGNALTHROTTLE_MODE`, `ENABLE_TRADE_PLANS`,
  `ENABLE_MARKET_CONTEXT`, `FINNHUB_API_KEY`.
- Storage: signal events, raw engine logs, pressure blocks/series, market
  snapshots, trade plans, and outcomes.
- Phase 2 imports in production graph: market router, outcome router/worker,
  Finnhub provider, and market-context enrichment from replay/finalizer.
- CI: no `.github/workflows` directory at baseline.

## Baseline verification

The pre-change suite completed with 158 passed and 1 skipped. Those tests
verified the legacy behavior; they did not prove observer containment.

## Containment target

The first change set adds no new database schema, typed outbox, Railway
activation, strategy logic, or execution integration. It freezes the runtime
boundary, excludes Phase 2 from the production image, and adds enforcement
tests and documentation.
