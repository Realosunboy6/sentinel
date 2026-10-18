# M1: Analyzer Core — Plan

## Owner Rulings (confirmed before implementation)

1. **Frontier in M1.** Spec §7 lists the Analyzer results sections ending with "efficient frontier
   with 'your portfolio' dot → regime badge." `frontier_chart()` is in ST4; the adapter calls
   `portlab.optimize` for frontier points + portfolio dot only. The Optimizer page, method picker,
   and weights table belong to M3.
2. **Regime badge in M1.** `detect_regime` in the adapter, badge in the Analyzer template.
   The full regime panel (VaR/ES histogram, traffic light, Kupiec table) stays in M2.
3. **Fixtures committed.** Use `adj_close` (spec §6). Record source + download date in
   `tests/fixtures/README.md`. Yahoo restates adjusted history: if a golden test misses by a hair,
   data vintage is the first suspect — stop-and-report, never edit the expected value.
4. **Lazy portlab import.** portlab imported inside `run_analysis()`, not at module level.
   The engine-unavailable page can render even when portlab is missing.
5. **Landing hero fallback.** Cold-start (no cached K5 result): render the design package's
   static SVG growth chart. Never a 500, never a fabricated live number.
6. **Kupiec LR tolerance.** Assert to 3 dp (0.009), matching spec §5.6's stated precision.

---

## Top-Level Overview

**Goal:** Deliver the full Analyzer page (`/analyze`) backed by real price data and the portlab
engine, including the results cache, share links (`/a/<slug>`), presets, and the landing page (`/`).

**Scope:**
- `apps/analysis/engine.py` — portlab adapter (only file that imports portlab)
- `apps/analysis/analyzer.py` — orchestration: load prices → canonicalize → cache → engine → serialize
- `apps/analysis/forms.py` — portfolio input form with all §7 validation rules
- `apps/analysis/charts.py` — chart payload serializers (§9 envelope)
- Views, templates, URLs for `/`, `/analyze`, `/a/<slug>`, `/api/tickers`
- `tests/fixtures/k5_prices.csv`, `tests/fixtures/spy_prices.csv` — committed price fixtures
- Golden-number regression tests + SPY anchor tests

**Gate:** `pytest` exits 0; golden test reproduces `metrics.json` within tolerance; SPY backtest
anchors (§5.6) pass; `/analyze` and `/a/<slug>` return 200 with chart payloads for the K5 preset.

**Out of scope for M1:** `/risk` full page (M2), `/optimize` page (M3), tool pages (M4).

---

## Sub-Task 1 — portlab engine adapter (`apps/analysis/engine.py`)

**Intent**
Single module that calls portlab. Owns the alpha-duality boundary (spec §5.1). Portlab import is
**lazy** (inside `run_analysis`) so the fail-closed error page renders even if portlab is absent.

**Expected Outcomes**
- `EngineUnavailableError(Exception)` defined in the module; raised inside `run_analysis` if
  `import portlab` fails (not at module load).
- `run_analysis(holdings, prices_df, benchmark_returns, tail_alpha=0.05) -> dict` where:
  - `holdings`: `[{"symbol": "MCK", "weight": 0.2998}, ...]`
  - `prices_df`: wide DataFrame of simple returns, one column per symbol
  - `benchmark_returns`: pd.Series of benchmark simple returns
- Alpha conversion (LOCKED per §5.1):
  - `portlab.risk.var.*` receives `alpha=tail_alpha` (e.g. 0.05)
  - `portlab.metrics.*` receives `alpha=1-tail_alpha` (e.g. 0.95 for confidence level)
- VaR stored as **positive number = loss** (spec §5.2).
- Frontier: calls `portlab.optimize` to get efficient frontier risk/return points + portfolio dot.
  No solver controls exposed — those are M3.
- Regime badge: calls `portlab.risk.regime.detect_regime`, returns the label string.
- Return dict shape matches `metrics.json`:
  `{portfolio, benchmark, annual, monthly, per_asset, var95, var99, es95, skew, exkurt, jb_p, hill,
   worst_day, best_day, pos_months, correlation, regime, frontier, data_vintage}`.

**Todo List**
1. Write `apps/analysis/engine.py`.
2. Add `EngineUnavailableError` to `apps/analysis/__init__.py`.

**Status:** [x] done

---

## Sub-Task 2 — Analysis orchestrator (`apps/analysis/analyzer.py`)

**Intent**
Layer between view and engine: load prices, compute returns, canonicalize, hash, check cache, call
engine on miss, store result, return metrics.

**Expected Outcomes**
- `analyze(holdings, start_date, end_date, benchmark_symbol) -> tuple[Analysis, dict]`
- `load_prices(symbols, start_date, end_date) -> pd.DataFrame` — query `PriceHistory.adj_close`,
  pivot to wide DataFrame, forward-fill up to 5 days (handle holidays), align all columns.
- Unknown ticker: call `ingest_security(symbol, YahooPriceSource())` on-demand before querying;
  raise `InvalidTickerError(symbol)` if `UnknownTickerError` is caught.
- `canonicalize(holdings) -> str` — sort by symbol, round weights to 6 dp, `json.dumps`.
- `input_hash(canonical) -> str` — `hashlib.sha256(canonical.encode()).hexdigest()`.
- Cache hit: `AnalysisResult.objects.filter(input_hash=..., data_asof=latest_date).first()`.
- Cache miss: call `engine.run_analysis(...)`, write `AnalysisResult`, create `Analysis` with slug.
- `gen_slug() -> str` — `secrets.token_urlsafe(9)[:8]`, re-roll until unique in `analyses`.
- `data_asof` = latest date in the loaded price DataFrame.
- `InvalidTickerError(symbol: str)` defined here.

**Todo List**
1. Write `apps/analysis/analyzer.py`.
2. Add `InvalidTickerError` to `apps/analysis/__init__.py`.

**Status:** [x] done

---

## Sub-Task 3 — Input form and validation (`apps/analysis/forms.py`)

**Intent**
Portfolio input form as a reusable component. All §7 validation rules enforced server-side.
Matches the `dashboard.html` mockup layout.

**Expected Outcomes**
- `PortfolioInputForm` validates: 1–25 holdings; weights ≥ 0; sum 100 ± 0.5 (show actual sum in
  error); duplicates merged with notice; tickers resolve (check `securities` table first, then
  live `source.validate()`); start date; benchmark symbol.
- Normalize action: POST `action=normalize` reweights to exactly 100%, re-renders form.
- Preset buttons: `GET /analyze?preset=k5-sample` → loads from `Preset` DB row → fills form.
- `GET /api/tickers?q=<prefix>` → JSON `[{"symbol": ..., "name": ...}]` from `securities` table
  (case-insensitive prefix match).
- Start-date default: 10 years back from today.
- Benchmark default: `SPY`.

**Todo List**
1. Write `apps/analysis/forms.py`.
2. Write `apps/analysis/views.py` stub with `tickers_autocomplete` view.
3. Write `templates/analysis/partials/portfolio_form.html`.

**Status:** [x] done

---

## Sub-Task 4 — Chart payload serializers + ECharts (`apps/analysis/charts.py`)

**Intent**
Convert engine output to §9-envelope JSON payloads. Vendor `echarts.min.js`.

**Expected Outcomes**
- `apps/analysis/charts.py` exports one function per chart (all return `{"chart", "title",
  "series", "meta": {"asof": ...}}`):
  - `growth_chart(dates, portfolio_values, benchmark_values, asof)`
  - `drawdown_chart(dates, drawdown_pct, asof)`
  - `annual_bars_chart(years, returns, asof)`
  - `monthly_heatmap_chart(years, months_matrix, asof)`
  - `allocation_donut_chart(symbols, weights, asof)`
  - `correlation_heatmap_chart(labels, matrix, asof)`
  - `frontier_chart(risk_return_points, portfolio_point, asof)`
- `static/echarts.min.js` — Apache ECharts 5 vendored (single file).
- Every payload includes hover tooltip config and the data-vintage label (spec §9).

**Todo List**
1. Write `apps/analysis/charts.py`.
2. Download `echarts.min.js` from the Apache ECharts CDN and save to `static/echarts.min.js`.

**Status:** [x] done

---

## Sub-Task 5 — Views, templates, URLs

**Intent**
Wire everything end-to-end. PRG pattern on form submit. Share links. Landing page with fallback hero.

**Expected Outcomes**
- `GET /analyze` → form (empty or preset-prefilled).
- `POST /analyze` → validate → run → **redirect** to `/a/<slug>` (PRG).
- `GET /a/<slug>` → load `Analysis` + `AnalysisResult`, render full results (read-only banner).
- `GET /` → landing page; hero chart = cached K5 result if it exists, else static SVG from
  `docs/design/index.html` (never a 500, never fabricated data).
- Engine down → `engine_unavailable.html` — clean error page, no traceback.
- "Share" button shows `/a/<slug>` with the disclaimer from spec §10.
- Results sections in mockup order (spec §7): KPI cards → growth chart → drawdown → performance
  table → annual bars → monthly heatmap → allocation donut → correlation heatmap →
  efficient frontier + portfolio dot → regime badge.
- `templates/base.html` updated with full nav (Analyze, Risk, Optimize, All tools) matching
  `dashboard.html` mockup chrome.

**Todo List**
1. Finish `apps/analysis/views.py` (analyze, shared_analysis, tickers_autocomplete).
2. Update `apps/core/views.py` with `landing_view`.
3. Write `templates/analysis/analyze.html`.
4. Write `templates/analysis/shared.html`.
5. Write `templates/core/index.html`.
6. Write `templates/analysis/engine_unavailable.html`.
7. Update `sentinel/urls.py` with all M1 routes.
8. Update `templates/base.html` nav.

**Status:** [x] done

---

## Sub-Task 6 — Golden-number tests + SPY anchor tests + fixtures

**Intent**
The M1 gate regression tests. Stop-and-report rule (LOCKED): if a number doesn't match, stop and
report — never edit the expected value.

**Expected Outcomes**
- `tests/fixtures/k5_prices.csv` — MCK, LLY, PWR, NVDA, STX, SPY adj_close, Jan 2021–Oct 2026,
  downloaded from Yahoo Finance, committed.
- `tests/fixtures/spy_prices.csv` — SPY adj_close, full available history, committed.
- `tests/fixtures/README.md` — records source (Yahoo Finance via yfinance), download date,
  column names, and the stop-and-report rule.
- `tests/test_golden.py` — calls `engine.run_analysis()` on the K5 fixture:
  - Portfolio CAGR, vol, Sharpe, Sortino, max DD, end value: `pytest.approx(x, rel=1e-4)`
    — source: `docs/design/snippets/metrics.json`
  - Per-asset (MCK/LLY/PWR/NVDA/STX) same fields: `rel=1e-3`
  - Annual returns 2021–2026: `rel=1e-4`
  - var95, var99, es95: `rel=1e-4`
- `tests/test_spy_anchors.py` — calls portlab backtest functions on SPY fixture:
  - 1,703 scored days, 86 exceptions — source: spec §5.6
  - Kupiec LR: `pytest.approx(0.009, abs=5e-4)` — spec §5.6
  - Christoffersen counts 1542/74/74/12 — spec §5.6
  - LR_ind: `pytest.approx(10.589773, rel=1e-4)` — spec §5.6
  - Joint LR: `pytest.approx(10.5987, rel=1e-4)` — spec §5.6

**Todo List**
1. Download fixtures via a one-shot script (not committed); commit the CSV outputs.
2. Write `tests/fixtures/README.md`.
3. Write `tests/test_golden.py`.
4. Write `tests/test_spy_anchors.py`.
5. Run both; investigate any mismatch in the adapter before touching expected values.

**Status:** [x] done

---

## Sub-Task 7 — Smoke tests + full pytest gate

**Expected Outcomes**
- `tests/test_pages.py` extended: GET `/`, GET `/analyze`, POST `/analyze` (K5 payload) →
  redirect to `/a/<slug>`, GET `/a/<slug>` → 200 + CAGR in content, GET `/api/tickers?q=SP` →
  200 + JSON with SPY.
- `pytest` exits 0 across all M0 + M1 tests.
- `README.md` updated: M1 ✅.

**Status:** [x] done

---

## Implementation Notes

- Sub-Tasks 3 and 4 can proceed in parallel with Sub-Task 2.
- Sub-Task 5 depends on all of 1–4.
- Sub-Task 6 depends on Sub-Task 1 only.
- Sub-Task 7 depends on all previous.
- Commit format: `M1.N: <description>` — e.g. `M1.1: portlab engine adapter`.
- Author: `Ibrahim Oyeyinka <ibrahimoyeyinka@yahoo.com>`.
- Do not push until the owner says "Push".
