# Build-contract review, 2026-10-18

## Follow-up, 2026-10-19

The implementation gaps identified below have been addressed:

- Analyzer and all three M3 pages now reuse `PortfolioInputForm`,
  `_portfolio_fields.html`, and `portfolio-input.js`. The editor includes
  add/remove rows, local Normalize, benchmark, start/end dates, inline errors,
  duplicate merging and finite/nonnegative weight validation. Tool submissions
  use cached data only. Edits are temporary and do not overwrite saved analyses.
- All Analyzer, RiskLens and M3 engine-error paths now use one response helper
  that logs a reference and displays that same reference without exception text.
- Drawdown charts annotate the actual minimum and its date. Both Analyzer and
  RiskLens use the updated serializer.
- Risk-contribution bars are horizontal, following the optimizer reference.
  The manual design review is recorded in `visual-review-m2-m3.md`.

Verification: **144 tests passed in 120.06 seconds**; Django check reported no
issues. There are 42 M3 tests, including the new form/error/annotation coverage.
Browser checks exercised add/remove, Normalize and POST computation, plus
reference-width and 390px layouts. Initial weight formatting was also checked.

M3 is ready for owner review of these changes. PostgreSQL/Python 3.12 execution
and the inherited schema discrepancies remain unverified/unresolved; they are
not marked passed. No locked schema, numerical fixtures or golden expectations
were changed. The original findings below are retained as review history.

This review corrects the earlier unqualified statements that M2 and M3 were
"complete". Their numerical milestone gates passed. That does not establish
full compliance with the shared product, design and database contracts.
This is a focused source review, not an exhaustive whole-project audit.

The live Analyzer submission check also succeeded: the shared editor submitted
the K5 portfolio and redirected to a saved report. It exposed two inherited M1
presentation issues outside this follow-up: the report header says "monthly
rebalanced" although the documented/tested engine path uses daily constant-mix
returns, and its regime badge displays `0` rather than a human-readable Calm
label. These are open items, not verified visual parity.

## Controlling documents

1. `SENTINEL-BUILD-SPEC.md`, including cross-cutting sections 7-10 as well
   as the milestone gate in section 12.
2. `docs/design/VISUAL-SPEC.md`, HTML mockups and reference screenshots.
3. The milestone plans, which cannot narrow requirements in the build spec.

## Original findings (2026-10-18)

| Requirement | Evidence | Status |
|---|---|---|
| Django 5 monolith, server-rendered templates, no frontend bundler | Existing settings and dependencies unchanged by M3; new pages extend `base.html` | Preserved |
| Existing design stylesheet and ECharts | New templates load the shared stylesheet through the base template and vendored ECharts | Preserved |
| Pinned portlab, no copied engine modules | `requirements.txt` still pins 0.2.2; new engine calls are in `apps/analysis/engine.py` | Preserved for new work |
| M3 method picker, frontier, allocation table, risk-parity and rolling pages | New views, templates and tests | Implemented |
| M3 numerical gate | Direct-call and database/web max-Sharpe checks at absolute tolerance 1e-4 | Passed |
| Existing numerical regressions | Last full run: 129 passed, including unchanged M1/M2 anchors | Passed |
| Editable shared portfolio form on tool pages, sections 7 and 8 | `_optimization_input.html` displays read-only holdings and links back to Analyzer; it does not reuse the dynamic portfolio form | **Missing** |
| Reference code for every engine-error panel, section 10 | Unexpected errors get a reference; `EngineUnavailableError` takes the generic 503 page without one | **Incomplete** |
| Visual contract, not merely visible charts | Basic desktop/390px checks were performed; a systematic comparison to reference shots was not. The risk-contribution bars also differ in orientation from the optimizer mockup | **Partial** |
| Drawdown deepest-point annotation, section 9 | Existing `drawdown_chart()` has no annotation; M2 reuses it | **Missing in M2** |
| PostgreSQL / Python 3.12 execution | Tests ran on SQLite / Python 3.14; PostgreSQL configuration was preserved | **Not verified** |

The mockup's Monte Carlo panel belongs to M4 under the milestone inventory;
its absence from M3 is not by itself a missing M3 implementation. Numerical
values must come from real fixtures/engine output, not copied mockup numbers.

## Inherited issues requiring separate reconciliation

- The Django models/migrations do not exactly reproduce the locked SQL schema:
  default Django table names are used, and `PriceHistory`/`AnalysisResult`
  have surrogate IDs plus uniqueness constraints where the SQL specifies
  composite primary keys. These originate in M0, not M2/M3. No schema changes
  were made during this review; reconciling the locked contract requires
  explicit decisions about existing databases and migrations.
- `analyzer._create_analysis()` imports portlab directly for its version,
  despite the adapter-only rule. This originates in M1. No new M3 path adds
  such an import outside the adapter.

## Acceptance state at the original review

M3's numerical gate is passed, but specification acceptance remains open.
Before advancing to M4, close the shared-input and error-reference gaps,
perform the reference-design comparison, and distinguish implementation
completion from untested environment coverage. Track the M2 annotation
follow-up as well. Do not call the whole application contract-compliant on
the strength of 129 passing tests.

## Timing

Bob's execution logs were not inspected, so no claim about why Bob took
longer is established. This continuation inherited the scaffold, M1 code,
partial M2 code, design package, committed fixtures and completed portlab
engine. It primarily added/changed adapters, views, templates and tests.
M2 also removed unused intermediate Student-t and GARCH fits when only the
final forecast was displayed. These facts explain work reused and a concrete
runtime reduction; they do not prove equivalent scope or review quality.
