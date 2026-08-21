# Test Skip Register

## Current skips

| Test | Classification | Reason | Release impact |
| --- | --- | --- | --- |
| `test_optional_sample_csv_parses_when_available` | `OPTIONAL_EXTERNAL_INTEGRATION` | A developer-local SignalThrottle sample CSV is not part of the repository. Fixture-based parser and sync tests remain active. | Non-critical |
| `test_owner_get_routes_and_replay_attempt_leave_postgres_state_unchanged` | `OPTIONAL_EXTERNAL_INTEGRATION` locally; mandatory in CI | Requires `TEST_DATABASE_URL`. GitHub Actions supplies an ephemeral PostgreSQL service and executes this test. | Critical CI gate |

Neither skip covers auth, production route inventory, Docker containment, or
the production image smoke test. The PostgreSQL checksum test must not be
skipped in CI.
