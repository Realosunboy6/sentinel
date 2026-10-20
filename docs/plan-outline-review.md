# M0–M3 outline compliance review

> **Repair follow-up (2026-10-19; staff-admin clarification approved by owner):** the findings below describe the pre-repair state. See [current acceptance evidence](repair-acceptance.md) for fixes, regression tests and remaining limits.

Reviewed 2026-10-19 against application commit `73e01d4`. This document records a solo review; it does not modify the build contract, implementation, fixtures, expected values or original milestone checklists.

## Conclusion

The project follows the intended milestone sequence and technology outline, but **not every planned outcome is satisfied**. M0/M1 should be reopened. M2's numerical gate is supported, with broader acceptance omissions. M3's own five implementation steps have evidence, but shared dependencies and prescribed-environment verification prevent an unconditional whole-project completion claim. Do not advance to M4 on the strength of existing checkmarks alone.

Reviewed in full: `m0-scaffold-plan.md`, `m1-analyzer-plan.md`, `m2-risklens-plan.md`, `m3-optimizer-plan.md`, `SENTINEL-BUILD-SPEC.md` and `docs/design/VISUAL-SPEC.md`. Inspected corresponding source, tests, fixture provenance, gate reports and relevant commit records. Existing baseline from the preceding audit: 144 tests passed in 127.91 seconds on Python 3.14/SQLite, Django check clean. Those tests were not rerun for this documentation-only outline check.

The distinction below matters: **code missing a plan item**, **code following a contradictory plan**, and **a requirement lacking verification** are different findings.

## M0 — six planned subtasks

| Step | Actual status | Evidence / remaining work |
|---|---|---|
| 1. Skeleton, Django, dependencies, Compose | Partial | Django/apps/templates/ECharts structure exists, pinned portlab 0.2.2 and PostgreSQL 15 image are present. The specified `scripts/refresh_prices.py` wrapper is absent. Compose has a literal default database password despite the plan's no-hardcoded-password requirement. The base design CSS is retained with added editor styles; it is no longer byte-identical, which is a documented extension rather than a wholesale framework replacement. |
| 2. Models and initial migration | Incorrect relative to contract; environment unverified | Default Django table names and surrogate price/result keys differ from the locked SQL. PostgreSQL migration/DDL inspection has not been demonstrated in the audit environment. Built-in admin/auth versus the plan's absolute no-users-table language remains a specification conflict. |
| 3. PriceSource and Yahoo adapter | Partial / defect | Interface and normalization tests exist, but validation searches only year 2000. The abstract method says validation returns bool; one plan test asks it to raise, so follow the explicit interface and reconcile the test wording. |
| 4. Ingestion and refresh command | Incomplete | Corporate actions are discarded; ordinary refresh cannot discover older price revisions; a failed history fetch leaves Security behind. History is capped at 1990 rather than maximum available. **Additional outline mismatch:** the plan says tracked securities plus `--symbols`, while the command refreshes only the explicitly supplied list when that flag is present. |
| 5. Admin, presets, twelve symbols, list page | Partial / unverified | Registrations, exact two presets, aggregate list view and smoke tests exist. A live twelve-symbol successful seed and displayed counts/latest dates have not been established by the mocked tests. |
| 6. Tests and gate | Partial | Tests and README instructions exist and the current suite passes; that does not establish the missing live-data/PostgreSQL gate outcomes. All six M0 plan statuses still say pending, inconsistent with README's completed label. |

## M1 — seven planned subtasks

| Step | Actual status | Evidence / remaining work |
|---|---|---|
| 1. Engine adapter | Partial / incorrect outputs | Lazy adapter and alpha conventions exist. Frontier mixes arithmetic return with a CAGR dot; Analyzer Hill uses absolute rather than loss returns; numeric regime labels are not mapped; short histories fail mandatory statistics. The tiny package-level exception re-exports requested by the plan were deliberately replaced with direct module imports; this is organizational, not a numerical failure. |
| 2. Orchestrator, canonical input, cache | Partial / plan conflict | Load/hash/cache/share path exists. Historical revision cache invalidation is missing. Canonical weights are rounded but not normalized, contrary to the architecture outline. Request-time ingestion follows this milestone plan but conflicts with locked cache-only requests. `analyzer._create_analysis` also imports portlab outside the single permitted adapter. |
| 3. Shared form and validation | Mostly implemented; exact planned POST action defective | Counts, finite/nonnegative weights, duplicate notices, dates, presets and autocomplete exist. The visible shared JavaScript Normalize works. However, **the planned `POST action=normalize` fails for out-of-tolerance totals**, because `form.is_valid()` rejects the total before normalization runs. A reproduced 50% submission gets “Use Normalize to fix” instead of normalization. It also fails to preserve end_date when that branch does run. This is distinct from the working browser button. |
| 4. Chart serializers / ECharts | Partial | Interactive serializers and vendored ECharts exist. Required growth log toggle and monthly annual column are absent. Exact heatmap/frontier hover contents need browser verification; merely having a tooltip config is insufficient. |
| 5. Views, templates, URLs | Partial / plan conflict | Main form, redirect, share disclaimer and read-only results exist. Landing selects an arbitrary latest result as K5. Static cold-start fallback follows an explicit M1 plan ruling, but its unlabeled numbers/static image conflict with global provenance and interactive-chart rules. `/api/analyze` is absent: it was omitted from the M1 route list even though the master route outline includes it. Rebalancing text and delivered-tool links are stale. |
| 6. Fixtures, goldens, SPY anchors | Implemented with recorded amendment; documentation stale | Committed fixtures, golden record and SPY anchor tests exist. Tests use `tests/fixtures/k5_golden.json`, not design `metrics.json`. Commit `dba5af5` and test comments record a 2026-10-16 ruling that the latter is a design mock. The plan, fixture README and master gate still name the older source. Preserve current evidence and reconcile the documents; do not treat this as permission to rewrite expectations. The ruling is repository-recorded; its original chat was not independently retrieved in this review. |
| 7. Smoke tests and full gate | Partial | Current suite passes. M1 POST tests mock the orchestrator, so they do not independently establish the entire real-price POST → engine → persisted report path. Earlier manual browser evidence exercised that path, but the identified acceptance defects remain. All seven plan statuses currently say done and overstate completion. |

## M2 — five planned subtasks

| Step | Actual status | Evidence / remaining work |
|---|---|---|
| 1. RiskLens engine | Core plan covered; broader contract incomplete | Five VaR methods, historical ES95, nullable-exception tests, separate Basel convention, tail/regime and designed short-history branches are present. The plan's payload only asks for ES95, while master §7 requests VaR/ES at 95/99; ES99 is absent. Analyzer's inconsistent Hill path is still separate technical debt. |
| 2. Risk charts | Implemented, with prior browser evidence | Histogram with numeric VaR lines, regime bars, vintage and drawdown annotation exist. No new pixel/hover acceptance pass is claimed here. |
| 3. Risk view / template | Plan substantially followed; global omission | Page sections, session-selected slug, source-free cached loading and errors exist. The plan explicitly calls it read-only; §8 requires a shared input on every tool, including RiskLens. No editor is present. Shared loader silently truncates stale holdings. |
| 4. Web SPY anchors | Verified by existing tests | Real committed prices are seeded into the test database; `/risk` response metrics assert the anchors. This is stronger evidence than the plan's suggested mocked page smoke test alone. Direct and web short-history tests exist. |
| 5. Full gate / README / commit | Numerical gate passed | Suite and commit evidence exist. Complete checklist labels should be understood as the numerical/local gate, not full global contract acceptance. |

## M3 — five planned steps

| Step | Actual status | Evidence / remaining work |
|---|---|---|
| 1. Optimizer adapter / constraints | Implemented with test evidence | All five required methods plus clearly labeled turnover-aware choice, Ledoit–Wolf covariance, explicit views, finite/budget/cap checks and direct portlab comparisons. No additional M3-specific numerical defect confirmed. |
| 2. Optimizer page | Implemented; shared-data caveat | Cached prices, preserved dates, edited portfolio/options, consistent frontier/dots, weights/risk contributions and cost estimates exist. Stale-history handling is inherited from the common loader. |
| 3. Risk-parity / rolling pages | Implemented with test evidence | Signature visuals/tables/links exist. Rolling samples exclude decision-date returns; drift is applied for subsequent turnover. It is explicitly an allocation study, not a strategy-return backtest. |
| 4. Fixture and web tests | Local numerical gate passed | Direct max-Sharpe tolerance, other methods, caps, invalid states, missing engine/data, views and rolling timing are covered. Direct-engine agreement is adapter verification, not independent proof of the library's optimization quality. |
| 5. Checks, browser, local commit, review stop | Local work recorded; review open | Existing test/system-check, desktop/mobile and local commit evidence is documented. Python 3.12/PostgreSQL execution remains open. Owner acceptance before M4 is correctly unchecked. |

M3's checkbox “close the identified implementation gaps” describes the earlier targeted follow-up, not every gap discovered by the broader M0–M3 review. Its visual review is also a scoped comparison, not certification of every global design rule on every page.

## What is following the outline

- Django templates, existing design CSS, vendored ECharts and public pinned portlab are retained; no frontend framework or bundler was introduced.
- Analyzer → RiskLens → Optimizer implementation order was followed in the commit history; M4 has not begun in the current tree.
- M3 includes the required risk-parity and rolling pages. Its extra turnover-aware method is explicitly in its plan, not unplanned scope.
- Monte Carlo and the remaining gallery belong to M4, deployment/walkthrough to M5. Their absence is not an M0–M3 defect. However, explicit M0 ingestion/schema and shared §7–10 requirements cannot all be deferred to M5's final hardening pass.
- Recent commits use the required author identity. M3 remains local and awaits review; this review did not fetch the remote or perform a push.

## Additional outline reproductions in this review

Three focused checks ran with an isolated in-memory database configuration and mocked external/control boundaries:

1. `refresh_prices --symbols NEW` called ingestion for NEW only, despite a mocked tracked universe containing TRACKED. The plan requires their union.
2. `POST /analyze` with `action=normalize` and a 50% total returned the weight-total validation error. This does not invalidate the already verified client-side Normalize button.
3. Holdings (.6, .4) and (.5988, .3992) have identical normalized ratios and the latter is within the form's sum tolerance, but produce different canonical hashes. Architecture §3 says normalize before hashing.

## Required reconciliation before advancing

First repair the confirmed ingestion, data-revision/cache and Analyzer defects. Then complete missing shared API/editor/chart requirements and verify the prescribed database/runtime. Reconcile the explicit plan/master conflicts and stale golden-source references without changing locked decisions or expected values implicitly. Finally update each original plan's status with scoped evidence, so “gate passed” and “all acceptance requirements complete” are no longer interchangeable.

The earlier detailed defect report and executable reproductions are in `C:/Users/ibrah/Downloads/sentinel-m0-m3-review.md`, `sentinel-audit-reproduce.py` and `sentinel-audit-results.json`. No application changes are included in this outline review.
