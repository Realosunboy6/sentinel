# M5 hardening and deployment plan

Prepared 2026-10-21 from §§10–14 of `SENTINEL-BUILD-SPEC.md` and the
current M4 gate record. This is a plan only. It authorizes no M5 code,
deployment, production data write, commit, or push.

## Gate definition

M5 is complete only when the production URL serves the application over
HTTPS, PostgreSQL backs it, the nightly cached-price refresh is installed
and observable, yesterday's cache remains usable after a failed refresh,
and the owner completes a walkthrough. A passing local suite alone is not
the M5 gate.

## Execution order

1. **Close the inherited M4 gate before hardening.** Repair or replace the
   unusable local PostgreSQL 15 runtime, run the full suite on PostgreSQL,
   and record the exact pass count and duration. Compare the tools gallery
   and representative chart-heavy reports at desktop and 390 px widths
   against `docs/design/shots/tools.png`. Fix only confirmed M4 defects;
   retain the disclosed factor, attribution, and tax assumptions unless
   the build contract is amended.

2. **Build an executable §10 edge-case matrix.** Add focused tests for
   unknown symbols leaving no rows, weight totals outside `100 ± 0.5`,
   normalization, fewer than 60 observations, stale/delisted holdings,
   stale benchmarks, interior gaps, invalid dates and parameters, missing
   portlab, and unexpected engine exceptions. Every HTML engine failure
   must show a log-correlated reference without a traceback; JSON failures
   must return the same safe contract. Confirm random share slugs and the
   public-by-link disclosure next to Share.

3. **Verify refresh/cache behavior under failure and concurrency.** Exercise
   unchanged, appended, revised, partial-failure, and total-failure refreshes
   on PostgreSQL. Confirm revisions expire derived results while preserving
   analyses and slugs; unchanged data retains cache entries; request and
   refresh locks prevent duplicate or mixed-vintage results; failed refreshes
   leave the prior prices and reports available with the older vintage shown.
   Record per-symbol success/failure in logs that staff can inspect.

4. **Harden the production Django configuration.** Add production-only
   settings for proxy HTTPS, secure cookies, CSRF trusted origins, strict
   hosts, static-file serving, structured application/refresh logging, and
   safe defaults with `DEBUG=False`. Run Django's deployment checks. Keep
   staff-only admin and anonymous public-by-link analyses; add no visitor
   accounts or ownership model.

5. **Create one reproducible deployment artifact.** Package Django with
   gunicorn and pinned dependencies in a container, include a health endpoint,
   collect static assets during build/release, and run migrations as an
   explicit release step. PostgreSQL remains a separate persistent service.
   Secrets and source settings come from environment variables; no `.env`,
   credentials, database dump, or portlab source enters the image or repo.

6. **Provision the selected host and HTTPS.** Before this step, select the
   actual VM/container platform and domain because those are not fixed by the
   spec. Configure the production database, application service, standard
   HTTPS terminator, allowed host/origin values, persistent logs, restart
   policy, and least-privilege environment. Create the staff administrator
   through the platform's protected shell.

7. **Install and prove the nightly refresh.** Schedule `refresh_prices` for
   01:00 UTC on weekdays. Seed the locked 12-symbol universe, verify counts
   and latest dates in staff-visible output, then force a controlled failed
   refresh and show that the public site still serves the prior cache and
   stale vintage. Restore the normal schedule after the drill.

8. **Run the production acceptance pass.** Execute migrations, Django deploy
   checks, the full PostgreSQL suite against an isolated test database, and
   HTTP smoke tests for every §7/§8 route. Walk desktop and mobile views for
   Analyze, shared analysis, RiskLens, optimization, all 19 tools, securities,
   safe 404/500 behavior, admin login, share disclosure, and chart tooltips,
   axes, exact values, and vintage labels. Check logs contain references but
   no secrets or visitor tracebacks.

9. **Finish operator documentation and stop for owner review.** Update the
   README with exact build, environment, migration, seed, run, refresh,
   backup/restore, rollback, log-inspection, and deployment commands for the
   chosen host. Record the deployed revision, URL, database/runtime versions,
   refresh evidence, test totals, known limitations, and rollback point in an
   M5 gate report. Stop for the owner's deployed walkthrough. Commit only
   coherent verified changes and never push without a new explicit `Push`.

## Stop conditions

- Any golden or SPY-anchor regression stops the line; expected values are not
  edited to make it pass.
- Any production-path synthetic market data, request-time source download,
  traceback exposure, cache corruption, secret in source/image/log output, or
  failed-refresh outage blocks deployment.
- A host choice, domain, or production credential is required only at step 6.
  Earlier hardening and container work can proceed after owner approval of
  this plan.

## Current implementation evidence (2026-10-21)

- Added safe database readiness, friendly 404/500 responses, log-correlated
  M4 tool failures, production proxy/cookie/HSTS/origin controls, structured
  stdout logging, WhiteNoise static assets, gunicorn, and a non-root container.
- Added a PostgreSQL-backed Compose service definition and explicit release
  commands. The production deployment check passes with production values;
  static collection succeeds. Seven focused M5 tests pass; the full SQLite
  regression result is **195 passed, 1 PostgreSQL-only concurrency skip in
  85.79 seconds**.
- Desktop visual review of the current process passes. A stale preview process
  from 2026-10-20 was identified and stopped after it served old gallery assets
  on the same port.
- Still open: the downloaded PostgreSQL 15 executable fails on this Windows
  build with `Illegal System DLL Relocation`, Docker is unavailable locally,
  and the current browser controller exposes no viewport-resize API for the
  required 390 px screenshot. No container build or PostgreSQL M5 gate is
  claimed from this host.
- Deployment steps 6–9 remain open: no platform/domain has been selected, no
  production service or scheduler exists, and no owner walkthrough has run.

- The 2026-10-22 deployment re-review defects were corrected before push:
  the internal health probe declares forwarded HTTPS, PostgreSQL binds only
  to loopback on the host, debug mode avoids manifest storage, and generic
  500 logs include the traceback correlated to the visitor reference.
- The corrected M5 tests, migration check, deployment check, static collection,
  and diff check pass. A subsequent full-suite rerun is blocked on this host by
  Windows Application Control rejecting unsigned Statsmodels extension modules;
  no security policy was weakened. The 195-pass result above predates that host
  policy failure and remains the latest completed full-suite result.
