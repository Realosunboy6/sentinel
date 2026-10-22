# M5 gate status

Updated 2026-10-22.

## Verified locally

- Production Django settings, safe 404/500 responses, database health check,
  WhiteNoise assets, gunicorn, and the non-root container definition are in
  place.
- Seven focused M5 tests pass. Migrations have no pending model changes,
  `check --deploy` reports no issues with production values, `collectstatic`
  succeeds, and `git diff --check` is clean.
- The latest completed full SQLite run is 195 passed with one PostgreSQL-only
  concurrency skip. A later rerun is blocked by Windows Application Control
  rejecting unsigned Statsmodels extension modules; the policy was not changed.
- Edge device emulation at 390 x 844 shows no horizontal overflow on the
  landing, Analyzer, RiskLens, Optimizer, tools gallery, or securities pages.

## Automated production gate

`.github/workflows/m5-production-gate.yml` provisions PostgreSQL 15 on Linux,
installs `requirements.lock`, applies migrations, compares the migrated schema
to the locked DDL, runs Django deployment/static checks, executes the full test
suite including PostgreSQL concurrency, and builds the container without
publishing it.

The workflow is present on `main`; its PostgreSQL and container results remain
pending. A red golden, SPY-anchor, schema, concurrency, deployment, or container
result blocks release.

## Gate still open

M5 is not complete until a host and domain are selected, HTTPS and persistent
PostgreSQL are provisioned, the weekday 01:00 UTC refresh is installed and its
failure fallback is demonstrated, backup/restore and rollback are recorded,
and the owner completes the deployed walkthrough. No production URL or
production database currently exists in the available environment.
