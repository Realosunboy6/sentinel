# M0: Scaffold + Data Layer — Plan

> **2026-10-19 repair follow-up:** use [repair acceptance](docs/repair-acceptance.md) for current evidence and [outline review](docs/plan-outline-review.md) for the original discrepancies. Numerical gates and full acceptance are reported separately. Owner review before M4 remains open.

## Owner Decisions (confirmed before implementation)

1. **Docker Compose:** include a `docker-compose.yml` for local PostgreSQL 15. The app reads `DATABASE_URL` from the environment in all environments; no hardcoded credentials anywhere.
2. **Data source:** `yfinance` stays as the v1 `PriceSource` implementation per spec §6.
3. **K5 weights:** `k5-sample` preset uses exact weights — MCK 0.2998, LLY 0.2355, PWR 0.1906, NVDA 0.1561, STX 0.1180.

## Top-Level Overview

**Goal:** Stand up the complete skeleton of the Sentinel repository so that every
subsequent milestone has a stable surface to build on.  
**Scope:** Repository layout (§4), Django 5.2 project, PostgreSQL schema migrated from
`sentinel-schema.sql`, a `PriceSource` abstraction with a Yahoo Finance implementation,
a nightly `refresh_prices` management command that seeds and refreshes the 12-ticker
universe, Django admin for `securities` and `presets`, and a single internal page that
lists every security with its price count and latest date.  
**Gate:** `pytest` is green (unit tests for ingestion logic); the securities-list page
loads in a browser and shows all 12 tickers.  
**Out of scope for M0:** The analyzer form, engine adapter, any chart rendering, share
links, any tool page. Those belong to M1+.

---

## Sub-Task 1 — Repository skeleton and Django project

**Intent**  
Create the exact directory tree specified in §4 and bootstrap the Django 5.2 project
(`sentinel/` project package, `apps/` sub-packages, `templates/`, `static/`). This
gives every later sub-task a clean place to drop files.

**Expected Outcomes**
- `manage.py` exists at the repo root and `python manage.py check` passes.
- `requirements.txt` lists pinned versions: `django>=5.0,<6`, `psycopg[binary]`,
  `pandas`, `numpy`, `scipy`, `portlab[opt]==0.2.2`, `pytest`, `pytest-django`.
- The four app packages (`core`, `marketdata`, `analysis`, `tools`) are registered
  in `INSTALLED_APPS` but contain only empty views/urls for now.
- `static/styles.css` preserves the design base, with shared editor/responsive additions; the reference file remains unchanged.
- `static/echarts.min.js` placeholder comment in place (actual vendored file can be
  dropped in later).
- `docker-compose.yml` at the repo root starts a `postgres:15` service; `DATABASE_URL`
  is read from the environment (via `python-decouple` or `dj-database-url`); a `.env.example`
  documents the variable, and `.env` is gitignored.

**Todo List**
1. Create directory tree: `sentinel/` (project pkg), `apps/core/`, `apps/marketdata/`,
   `apps/analysis/`, `apps/tools/`, `templates/`, `static/`, `scripts/`, `tests/`.
2. Run `django-admin startproject sentinel sentinel/` (or write `settings.py` /
   `urls.py` / `wsgi.py` / `asgi.py` by hand to avoid clobbering the repo root).
3. Write `requirements.txt` with all pinned deps listed above; add `dj-database-url`
   and `python-decouple` (or equivalent) for `DATABASE_URL` parsing.
4. Write `docker-compose.yml` with a `postgres:15` service (no hardcoded passwords;
   credentials via env vars). Add `.env.example` with `DATABASE_URL=postgres://sentinel:sentinel@localhost:5432/sentinel`,
   `SECRET_KEY=`, `DEBUG=True`. Add `.env` to `.gitignore`.
5. Register apps, wire `ROOT_URLCONF`, set `TEMPLATES` dirs, `STATICFILES_DIRS`.
6. Copy `docs/design/styles.css` → `static/styles.css`.
7. Add a `pytest.ini` (or `pyproject.toml [tool.pytest.ini_options]`) pointing
   `DJANGO_SETTINGS_MODULE` at the project settings.

**Relevant Context**
- Spec §4 (repo layout)
- Spec §2 (stack: Django 5, Python 3.12, PostgreSQL 15+)
- `docs/design/styles.css` — base stylesheet to copy verbatim

**Status:** [x] implemented and locally tested; see repair acceptance for environment/live-data gate

---

## Sub-Task 2 — Database models and initial migration

**Intent**  
Translate `sentinel-schema.sql` into Django ORM models inside `apps/marketdata/`
(for `securities`, `price_history`, `corporate_actions`) and `apps/analysis/` (for
`analyses`, `analysis_results`, `presets`), then generate and apply the initial
migration. Using `NUMERIC` fields and `DateField` throughout, exactly as the schema
specifies.

**Expected Outcomes**
- `apps/marketdata/models.py` contains `Security`, `PriceHistory`,
  `CorporateAction`.
- `apps/analysis/models.py` contains `Analysis`, `AnalysisResult`, `Preset`.
- `python manage.py migrate` runs cleanly against a local PostgreSQL 15+ database.
- `python manage.py dbshell` → `\dt` shows all six tables.
- No visitor-account or portfolio-ownership models are introduced. Owner clarification (2026-10-19): retain staff-only Django admin and its framework auth tables; the no-accounts rule applies to visitors.

**Todo List**
1. Write `apps/marketdata/models.py`:
   - `Security` — `id` UUIDField PK, `symbol` TextField, `exchange` TextField,
     `name` TextField nullable, `asset_type` TextField, `currency` CharField(3).
     `unique_together = [('symbol', 'exchange')]`.
   - `PriceHistory` — composite PK `(security, date)`, `open/high/low/close`
     `DecimalField(18,4)` nullable except `close`/`adj_close`, `volume` BigIntegerField.
   - `CorporateAction` — UUID PK, FK to Security, `ex_date` DateField,
     `action_type` CharField with choices, `ratio` DecimalField(18,6).
     `unique_together = [('security', 'ex_date', 'action_type')]`.
2. Write `apps/analysis/models.py`:
   - `Analysis` — UUID PK (no auto-increment), `slug` unique TextField,
     `input_hash` TextField (indexed), `inputs` JSONField, `engine_version` TextField,
     `created_at` DateTimeField auto.
   - `AnalysisResult` — composite PK `(input_hash, data_asof)`, `metrics` JSONField,
     `computed_at` DateTimeField auto.
   - `Preset` — `slug` TextField PK, `name`, `inputs` JSONField.
3. Create and apply migrations: `makemigrations marketdata analysis`.
4. Verify `migrate` completes without errors; spot-check the schema with `dbshell`.

**Relevant Context**
- `docs/design/sentinel-schema.sql` — authoritative DDL; the models must match it
  field-for-field.
- `docs/design/sentinel-db-design.md` — narrative explanation of each table.
- Spec §6 — LOCKED schema rules (NUMERIC not float, no identity columns on analyses,
  slug = short base62 token).

**Status:** [x] implemented and locally tested; see repair acceptance for environment/live-data gate

---

## Sub-Task 3 — PriceSource abstraction and Yahoo Finance implementation

**Intent**  
Define the `PriceSource` interface in `apps/marketdata/sources.py` so that the Yahoo
Finance implementation is one concrete class, and swapping to a second source later
touches only one file. The interface covers two operations: validate-ticker and
fetch-OHLCV.

**Expected Outcomes**
- `apps/marketdata/sources.py` defines an abstract `PriceSource` with `validate(symbol)`
  and `fetch(symbol, start, end)` methods.
- `YahooPriceSource` implements that interface using `yfinance`.
- `yfinance` is added to `requirements.txt`.
- Unit tests in `tests/test_sources.py` mock `yfinance` and verify that the adapter
  normalizes column names, returns a DataFrame with columns
  `[date, open, high, low, close, adj_close, volume]`, and raises a clean
  `UnknownTickerError` for a bogus symbol.
- No test hits the real network.

**Todo List**
1. Add `yfinance` to `requirements.txt`.
2. Write `apps/marketdata/sources.py`:
   - `class UnknownTickerError(Exception)`.
   - `class PriceSource(ABC)` with abstract methods `validate(symbol: str) -> bool`
     and `fetch(symbol: str, start: date, end: date) -> pd.DataFrame`.
   - `class YahooPriceSource(PriceSource)` wrapping `yfinance.download`; raises
     `UnknownTickerError` if the returned DataFrame is empty.
3. Write `tests/test_sources.py` with at least:
   - `test_fetch_normalizes_columns` — mock `yfinance.download` returning a known
     DataFrame; assert column set and dtypes.
   - `test_validate_unknown_raises` — mock returns empty DataFrame; assert
     `UnknownTickerError` is raised.

**Relevant Context**
- Spec §6 (data source: Yahoo Finance behind a `PriceSource` interface, one impl in v1).
- Spec §10 (unknown ticker → clean error, nothing stored).

**Status:** [x] implemented and locally tested; see repair acceptance for environment/live-data gate

---

## Sub-Task 4 — Ingestion service and `refresh_prices` management command

**Intent**  
Implement the logic that populates `securities` and `price_history` rows from the
`PriceSource`, then wrap it in a Django management command callable as
`python manage.py refresh_prices`. This command is also the seed mechanism: it
accepts a `--symbols` flag so M0 can seed the 12-ticker universe.

**Expected Outcomes**
- `apps/marketdata/ingestion.py` contains `ingest_security(symbol, source)` that:
  - creates a `Security` row if none exists (validate first; raise `UnknownTickerError`
    if the source rejects it).
  - fetches full history from the source and bulk-upserts into `price_history` (no
    duplicate rows; new days are appended).
  - inserts `corporate_actions` rows (splits/dividends) if the source provides them.
- `apps/marketdata/management/commands/refresh_prices.py` calls `ingest_security`
  for every tracked security (all rows in `securities` by default) plus any symbols
  passed via `--symbols`.
- Running `python manage.py refresh_prices --symbols SPY QQQ BND` against a live DB
  produces rows in `securities` and `price_history`.
- Unit tests mock the source and assert that `ingest_security` calls `validate`,
  calls `fetch`, and writes the expected number of `PriceHistory` rows.

**Todo List**
1. Write `apps/marketdata/ingestion.py` with `ingest_security(symbol, source)`.
2. Handle the upsert: use `bulk_create(update_conflicts=True, update_fields=[...])` 
   (Django 5 supports this for PostgreSQL).
3. Write `apps/marketdata/management/__init__.py`,
   `apps/marketdata/management/commands/__init__.py`,
   `apps/marketdata/management/commands/refresh_prices.py`.
4. Write `tests/test_ingestion.py` with at least:
   - `test_ingest_creates_security_row`.
   - `test_ingest_appends_price_rows`.
   - `test_ingest_unknown_ticker_raises_and_does_not_create_row`.

**Relevant Context**
- Spec §6 (ingestion rules: validate before create; nightly refresh appends; no row
  mutation on old prices).
- Spec §3 (nightly job = management command `refresh_prices`).
- Sub-Task 3 (source interface and `UnknownTickerError` defined there).

**Status:** [x] implemented and locally tested; see repair acceptance for environment/live-data gate

---

## Sub-Task 5 — Django admin, seed data, and securities-list page

**Intent**  
Register `Security`, `Preset`, and `CorporateAction` with the Django admin so the
owner can inspect and curate data. Seed the two required presets and the 12-ticker
universe into the database. Build the one visible page required by the M0 gate: a
securities list at `/securities/` (or `/admin/` overlay is acceptable if the gate is
met) that shows each security's symbol, latest price date, and row count.

**Expected Outcomes**
- `python manage.py createsuperuser` + `/admin/` shows `Securities`, `Presets`, and
  `Corporate Actions` sections.
- A data migration or management command `seed_presets` inserts:
  - `60-40`: `[{"symbol":"SPY","weight":0.60},{"symbol":"BND","weight":0.40}]`
  - `k5-sample`: MCK 0.2998, LLY 0.2355, PWR 0.1906, NVDA 0.1561, STX 0.1180 (exact weights, confirmed by owner).
- Running `python manage.py refresh_prices --symbols SPY QQQ BND AAPL MSFT IWM GLD MCK LLY PWR NVDA STX`
  seeds all 12 tickers.
- `GET /securities/` returns an HTML page listing all securities with: symbol, exchange,
  latest `price_history.date`, count of price rows. No chart required; a plain HTML
  table is fine.

**Todo List**
1. Write `apps/marketdata/admin.py` registering `Security`, `PriceHistory`,
   `CorporateAction` with list displays showing symbol, latest date, row count.
2. Write `apps/analysis/admin.py` registering `Preset` with `slug`, `name`, `inputs`.
3. Write a data migration (or `seed_presets` management command) that inserts the
   two preset rows.
4. Add a `securities_list` view in `apps/core/views.py` that queries
   `Security` joined to `price_history` aggregated by `(symbol, count, max date)`.
5. Wire `/securities/` URL in `sentinel/urls.py` → `core.views.securities_list`.
6. Write `templates/core/securities_list.html` extending a `base.html` with the
   nav chrome from the design (`styles.css` already in `static/`).
7. Smoke test: `tests/test_pages.py` → `GET /securities/` returns 200.

**Relevant Context**
- Spec §6 (presets: DB rows, seed with `60-40` and `k5-sample`; 12-ticker seed universe
  from `docs/design/snippets/metrics.json`).
- Spec §12 M0 gate: "a page lists securities with price counts and latest dates."
- `docs/design/styles.css`, `docs/design/index.html` — chrome reference for `base.html`.

**Status:** [x] implemented and locally tested; see repair acceptance for environment/live-data gate

---

## Sub-Task 6 — Pytest suite wired and gate confirmed

**Intent**  
Ensure the full `pytest` suite runs cleanly (no network calls, no live DB in unit
tests) and the M0 gate criteria are verifiably met: all tests green, the securities
page loads.

**Expected Outcomes**
- `pytest` exits 0 with all tests collected and passing.
- No test hits the real network or requires a running database (unit tests use mocks;
  the page smoke test uses `pytest-django`'s `db` fixture against a test DB).
- A `conftest.py` provides a shared `mock_source` fixture and the Django test client.

**Todo List**
1. Write `tests/conftest.py` with fixtures: `mock_source` (a `PriceSource` stub),
   `client` (Django test client), and any shared price-data DataFrame fixtures.
2. Confirm all test files import correctly and `pytest --collect-only` shows ≥ 8 tests.
3. Run `pytest` — fix any failures.
4. Document the seed + run steps in `README.md`: how to create the DB, run migrations,
   seed prices, and start the dev server.

**Relevant Context**
- Spec §13 (testing requirements: unit tests with fixed fixtures, no network, no
  fabricated numbers).
- Spec §12 M0 gate: "`pytest` green; a page lists securities with price counts and
  latest dates."

**Status:** [x] implemented and locally tested; see repair acceptance for environment/live-data gate

---

## Context for Implementation

- All sub-tasks are ordered and each one unblocks the next. Start at Sub-Task 1.
- After each sub-task, update its `Status` line to `[x] done` before starting the next.
- Commit message format: `M0.N: <short description>` (e.g. `M0.1: repo skeleton and Django project`).
- Author: `Ibrahim Oyeyinka <ibrahimoyeyinka@yahoo.com>`.
- Do not push until the owner says "Push".
