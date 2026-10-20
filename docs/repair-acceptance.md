# M0–M3 repair acceptance

2026-10-19. Implementation commit: `c0e5624`. Implements the user's instruction to fix the findings in the solo code and outline reviews. This report supersedes the earlier unqualified completion labels. M4 is not started; no push is authorized by this repair request. The staff-admin wording conflict was resolved by the owner during the repair.

## Repairs delivered

| Review finding | Corrected behavior |
|---|---|
| Fixed year-2000 ticker validation | Yahoo validation uses available maximum history. Modern listings BND, GLD and STX passed the live seed. |
| Missing corporate actions | Source preserves split/dividend events in DataFrame metadata; ingestion upserts them atomically with prices. |
| Failed ingestion leaves securities | Validate/download precede any new rows; persistence is atomic. Failed history fetches leave no new security. |
| Incomplete historical refresh | Default refresh reconciles maximum history, including adjusted-close revisions and pre-1990 prices. Explicit starts remain available for scoped operations. |
| Stale result cache | Revisions expire derived results while retaining inputs/slugs. Cache hits verify actual loaded prices plus an adapter-report version fingerprint. PostgreSQL refresh/request locks protect cache fills against concurrent writers. |
| Refresh flag skips tracked symbols | Command takes the union of tracked securities and explicit symbols. `scripts/refresh_prices.py` now provides the planned wrapper. |
| Locked schema mismatch | Additive, reversible upgrade migrations give the six required table names, real composite price/result primary keys, SQL types/defaults, action CHECK and cascading foreign keys. No canonical SQL file was changed. |
| Incompatible frontier coordinates | Analyzer's portfolio dot now uses the same annual arithmetic-return basis as its frontier. CAGR remains the performance KPI. |
| Inconsistent tail/regime labels | Analyzer Hill receives losses, as RiskLens does. Regimes map to Calm/Stressed/Unknown. |
| Short histories fail | Per-statistic availability gates replace mandatory Jarque–Bera/Hill calls. One-return Analyzer/API/share/RiskLens paths render safely, without NaNs or false risk estimates. |
| Unknown/stale/missing cached data | Requests never download. Unknown symbols receive an inline cache message. Stale/unavailable holdings are listed, excluded and renormalized visibly; stale benchmarks and long interior gaps block analysis. Securities list flags stale history. |
| Wrong K5 attribution / fabricated fallback | Landing selects a matching dated K5 analysis, displays its actual vintage, and shows an honest unavailable state without static design numbers. |
| Missing API and normalization | `/api/analyze` returns JSON metrics/charts/share URL. Canonical inputs normalize before hashing. Server-side Normalize accepts incorrect positive totals and preserves both dates. |
| Missing chart requirements | Growth linear/log control; compounded annual heatmap column; correct period/value and frontier tooltips; blue-positive correlation palette. Heatmap legends and mobile tables are contained within their cards. |
| RiskLens omissions | Shared editable cached-data form and ES99, with direct-engine expected-shortfall verification. Editing creates/selects an analysis rather than mutating old inputs. |
| Stale descriptions and navigation | Daily constant-mix label, working Risk/Optimize links, responsive navigation, updated fixture provenance and plan/gate status references. |
| Compose credentials | Password fallback removed; environment example and setup instructions require an explicit local password. |

## Verification

- Full Python 3.12.14 / Django 5.2.18 / PostgreSQL 15.19 suite: **167 passed in 98.11 seconds**. A final focused ingestion/source check passed **20 tests in 3.36 seconds**, including consistent half-tick rounding and unchanged-data cache retention.
- Full Python 3.14 / SQLite suite: **166 passed, 1 PostgreSQL-specific concurrency test skipped in 112.68 seconds**. The final focused ingestion/source recheck also passed **20 tests in 6.77 seconds**.
- Existing 52 golden/SPY-anchor tests passed unchanged during the repair. Numerical expectations and price CSVs were never edited.
- Regression coverage includes available-history validation, actions, rollback, same-date revisions, canonical ratios, POST Normalize, source-free requests, stale holdings/gaps, short histories, API/share/editor integration, SQL checks and data-preserving migration. PostgreSQL-specific concurrency coverage checks identical simultaneous submissions produce one calculation/result.
- `scripts/verify_postgres_schema.py` executed the supplied DDL in a temporary reference schema and matched **all columns, SQL types, nullability, defaults and primary keys for all six business tables**, with database-level cascade checks.
- Migration regression on PostgreSQL and SQLite preserves prices, actions, preset content, analysis UUIDs/slugs and cached metrics. Separately, the copied fixture database retained **8,724 price rows** with identical before/after SHA-256 `43db69d1f77b92de3f8d6c5171ca413d2d190d8e48d8f0d4b6a6340accdfc2bb` over the business columns.
- Live Yahoo refresh on isolated PostgreSQL: **12 succeeded, 0 failed; 96,223 prices; 1,268 cash dividends and 28 splits**. All latest dates were 2026-10-19. AAPL/MSFT/LLY include pre-1990 history. `/securities/` returned 200 and visibly listed twelve counts/latest dates in the browser. Structured evidence: [live seed](verification/m0-live-seed.json).
- Browser fixture checks: growth scale button switches; monthly tooltip shows period and return; annual heatmap column and Calm badge render; RiskLens ES99 renders and editing its end date successfully creates/selects the recalculated report. At 390px, RiskLens document width is 375px with the scrollbar, and wide tables scroll inside cards. Final mobile navigation is a native Menu control.
- Fixtures and live-ingestion evidence are separate: no live downloads overwrote a committed regression fixture. The live database is an isolated verification instance, not a production deployment.

## Specification reconciliation

1. The locked cache-only request rule controls over M1's on-demand source calls and the contradictory §6 first-request wording. Ingestion belongs to the refresh job.
2. The real-data and interactive-visual rules control over the older static landing fallback. A cold start is explicitly unavailable.
3. The existing repository-recorded 2026-10-16 golden ruling uses `tests/fixtures/k5_golden.json`; the design snippet is illustrative. Commit `dba5af5` and the original test comments record that ruling. This repair updates stale plan/provenance references and does not create or revise expected values.
4. Composite keys require Django 5.2 within the prescribed Django 5 family. Django 5.2 does not register composite-key models in its standard admin. Required securities, presets and corporate-action administration remains; price/result records remain accessible through the ORM and securities summaries.
5. Corrected source history cannot reuse an obsolete derived result under the date-only cache key. Results are expired/recomputed, not numerically patched; saved inputs and share links remain. The locked business schema is retained.

## Owner decision resolved

The owner explicitly answered on 2026-10-19: **“Keep staff-only Django admin; clarify the no-accounts rule applies to visitors.”** The build spec and M0 plan now record this exception. Django's existing staff-auth tables remain for administrative curation; no public accounts, registration, identity/ownership models, brokerage connections or visitor-login flow were added.

## Reproduction and remaining limits

Run the full suite with the environment commands in README. For the locked PostgreSQL comparison, set `DATABASE_URL` to the isolated migrated database and run `python scripts/verify_postgres_schema.py`. The temporary reference schema is removed afterward. The temporary PostgreSQL server was stopped after verification; its isolated data remains available for reproduction. The fixture preview remains at `http://127.0.0.1:8767/`. The local verification runtime and downloaded [official EDB binaries](https://www.enterprisedb.com/download-postgresql-binaries) are outside the repository in Downloads.

Owner acceptance before M4 and the M5 deployed walkthrough remain open. This repair verifies the specified local runtime, live seed and the targeted UI behavior; it does not claim exhaustive pixel identity or independent mathematical certification of every portlab solver.
