# Sentinel: Build Specification for Bob

**What this document is.** The complete build brief for Sentinel, a public
portfolio risk analyzer. It is written to be dropped into the root of the
`sentinel` repo and executed milestone by milestone. Sections marked
**LOCKED** are decisions already made by the owner. Implement them, do not
relitigate. Sections marked **DEFAULT** are recommendations with a stated
default: follow the default unless the owner overrides in chat.

**Companion files (copy into `docs/design/` in the repo before starting).**
From the design package: `index.html`, `dashboard.html`, `risk.html`,
`optimize.html`, `tools.html`, `styles.css`, `VISUAL-SPEC.md`,
`sentinel-db-design.md`, `sentinel-schema.sql`, `snippets/` (19 reference
chart SVGs + `metrics.json` golden numbers), `shots/` (rendered mockup
screenshots). The mockups are the pixel reference; `VISUAL-SPEC.md` is the
visual contract; the schema files are the database contract.

---

## 1. Product definition

Sentinel is a Portfolio Visualizer-class web app with a deeper risk engine:
a visitor enters **tickers + weights**, presses Analyze, and gets
institutional-grade performance, risk, backtest, and optimization analysis
with a signature interactive chart for every tool.

### Hard constraints (LOCKED)

1. **No login, no accounts, no brokerage connection, no user money, ever.**
   There is no `users` table and there must never be one. The input is
   tickers + weights only. Do not build auth "for later."
2. **Every tool ships with at least one signature interactive visual**
   (matrix in §8). A tool that renders only numbers is not done.
3. **Real market data only.** No synthetic series in production paths.
   Synthetic data is acceptable only inside clearly-labeled unit tests.
4. **Requests never call the market-data source.** All analysis reads from
   the local `price_history` cache, refreshed by a nightly job (§6).
5. **The analysis engine is `portlab`, now a public MIT library**
   (`Realosunboy6/portlab`, pinned at `portlab==0.2.2` on PyPI).
   Install it as a pinned dependency, never vendor or copy its
   source into this repo (§5). As of the 2026-10-16 amendment (§5)
   the library is complete: every module this spec names is in the
   pinned release, and no tool is phased or held back.
6. **Design language (from VISUAL-SPEC.md):** navy `#10233f` chrome, page
   background `#f6f8fb`, white cards (10px radius, 1px `#e2e8f0` border,
   soft shadow), emerald `#0e9f6e` accent/positive, red `#dc2626`
   negative, amber warnings. System font stack. Tabular numerals for all
   money/percent figures. No dark mode in v1. No gradients except the
   landing hero. No stock photography.

## 2. Stack (DEFAULT)

- **Framework: Django 5 (Python 3.12)**: one monolith: server-rendered
  pages (templates), Django ORM over the schema in §6, Django migrations
  generated from `sentinel-schema.sql`, built-in admin for `presets` and
  `securities` curation. Rationale: the schema is relational and already
  designed; the owner wants hands-on database work, and Django's ORM +
  migration tooling is the shortest honest path. (If the owner overrides
  to Flask, keep every other section of this spec unchanged and swap the
  ORM to SQLAlchemy + Alembic.)
- **Database: PostgreSQL 15+** exactly per `sentinel-schema.sql`.
- **Charts: Apache ECharts** (single vendored JS file, no build step),
  fed by JSON payloads rendered server-side (§9). It covers every visual
  in the matrix: line/area, bars, heatmaps, scatter/frontier, fan
  charts, waterfall, with the required hover crosshairs and tooltips.
- **No frontend framework, no bundler in v1.** Django templates + ECharts
  + the design package's `styles.css` as the base stylesheet.
- **Tests: pytest + pytest-django.** Playwright for smoke/screenshot
  checks against the mockups.

## 3. Architecture

```
Browser ──► Django (pages + JSON endpoints)
                │
                ├── ORM ──► PostgreSQL (securities, price_history,
                │            corporate_actions, analyses,
                │            analysis_results, presets)
                │
                └── engine adapter (sentinel/engine.py)
                        └── portlab (public package, §5)

Nightly job (cron / management command):
    refresh_prices ──► data source ──► price_history + corporate_actions
                    ──► bumps data vintage ──► stale cache rows age out
```

Request flow for an analysis: validate input → canonicalize (sort
holdings, normalize weights) → `input_hash = sha256(canonical JSON)` →
look up `analysis_results(input_hash, data_asof = latest price date)` →
hit: render from cache; miss: load adjusted prices from `price_history`,
build returns, call the engine, store metrics JSON, render. Every results
page displays the data vintage ("history Jan 2021 to Oct 2026").

## 4. Repository layout (build exactly this shape)

```
sentinel/
  SENTINEL-BUILD-SPEC.md        <- this file
  README.md
  manage.py
  requirements.txt              <- django, psycopg, pandas, numpy, scipy
  sentinel/                     <- project package (settings, urls, wsgi)
  apps/
    core/                       <- landing page, base templates, static
    marketdata/                 <- securities/prices models, ingestion
    analysis/                   <- input form, analyzer, engine adapter,
                                   results cache, share links
    tools/                      <- the 18 tool pages (§8)
  templates/  static/           <- styles.css (from design), echarts.min.js
  docs/design/                  <- the design package, copied verbatim
  scripts/refresh_prices.py     <- nightly job entry (mgmt command wrapper)
  tests/
```

## 5. Engine integration: portlab (READ CAREFULLY)

**Amendment 2026-10-16: the engine is complete and on PyPI.**
portlab 0.2.0 (2026-10-16) published the complete toolkit, and 0.2.2
is the current release. The full module set is public: `metrics`,
`returns`, `covariance`, `risk` (var/backtest/tail/regime/monitor/
rebalance), `backtest`, `optimize`, `attribution`, `rebalance`,
`montecarlo`, `factor`, `alm`, `derivatives`, `indicators`,
`tactical`, `forecast`, `stress`, `scenarios`, `taxlots`, `taxopt`,
`mpo`, `analytics`, `data`, `plots`, `report`. This supersedes the
2026-10-12 amendment (which published a v0.1.0 core and held the
rest back) in every respect where they differ. Therefore:

- **Never** copy portlab source into this repo, not even a single
  module: install it as a dependency instead.
- Access pattern (DEFAULT): an adapter module `apps/analysis/engine.py`
  that is the *only* place importing `portlab`. Install pinned from
  PyPI: `pip install portlab==0.2.2` (add the `opt` extra,
  `portlab[opt]==0.2.2`, for the cvxpy solver backend). All engine
  calls go through the adapter, which converts Django-side inputs
  (symbols, weights, dates) to portlab's pandas inputs and converts
  results to JSON-safe dicts.
- **Nothing is held back.** Every module named in the engine map
  below is in the pinned release. Build every tool in §8; do not
  mark any gallery card "coming with a later portlab release" and
  do not build substitutes for engine functionality.
- If portlab is not importable, the site must fail closed with a clear
  "engine unavailable" page: never fabricate numbers.

### Engine map (tool → portlab module)

| Need | portlab entry points |
|---|---|
| Performance metrics | `portlab.metrics` (returns, vol, Sharpe, Sortino, max DD, CAGR) |
| VaR / ES family | `portlab.risk.var`: `historical_var`, `parametric_var`, `parametric_var_t`, `cornish_fisher_var`, `expected_shortfall`, `garch_var` |
| VaR backtests | `portlab.risk.backtest`: `exceptions`, `kupiec_pof`, `christoffersen_ind`, `joint_test`, `basel_traffic_light` |
| Regime | `portlab.risk.regime`: `detect_regime`, `regime_var`, `ewma_vol` |
| Tail diagnostics | `portlab.risk.tail` (Jarque-Bera, Hill) |
| Optimization | `portlab.optimize` (max-Sharpe, GMV, risk parity, min-CVaR, Black-Litterman, HRP where available) |
| Backtest engine | `portlab.backtest` (rebalancing backtests) |
| Monte Carlo | `portlab.montecarlo` |
| Factor analysis | `portlab.factor` |
| Attribution | `portlab.attribution` (Brinson) |
| Asset-liability | `portlab.alm` |
| Options | `portlab.derivatives` (Black-Scholes, Greeks, payoff) |
| Indicators / tactical | `portlab.indicators`, `portlab.tactical` |
| Forecasting | `portlab.forecast` (ARIMA/ETS) |
| Stress / scenarios | `portlab.stress`, `portlab.scenarios` |
| Tax | `portlab.taxlots`, `portlab.taxopt` |
| Covariance | `portlab.covariance` (incl. Ledoit-Wolf) |

### Engine conventions: do not relearn these the hard way

1. **`alpha` means different things in different modules.** In
   `portlab.metrics.*` and `optimize.cvar`, `alpha` is a *confidence
   level* (0.95). In `portlab.risk.var.*`, `alpha` is a *tail
   probability* (0.05). The adapter must convert at the boundary and
   name its own parameters unambiguously (`tail_alpha`).
2. **VaR sign convention:** portlab VaR is a *positive* number = loss.
   Returns are simple returns, positive = gain. An exception is
   `returns < -VaR`.
3. **`exceptions()` returns a nullable-boolean Series** (True/False on
   scored days, `<NA>` on unscored warmup/gap days). Do **not**
   `dropna()` it before `christoffersen_ind` (that re-joins gaps), do
   not `.astype(bool)` it (raises on `<NA>`); fill with False only for
   display copies.
4. **`garch_var` / `parametric_var` take `mean="zero"|"constant"`**
   (defaults: `"zero"` for GARCH, `"constant"` for parametric). Keep
   the defaults in v1.
5. **Forecast alignment:** rolling estimators stamp day *t* with a
   forecast built from data strictly before *t*. Do not "fix" this.
6. **Verified anchors** (SPY, real data, for golden tests): rolling-250
   historical VaR backtest: 1,703 scored days, 86 exceptions, Kupiec
   LR 0.009; Christoffersen counts 1542/74/74/12, LR_ind 10.589773;
   joint LR 10.5987. Max-Sharpe vs PyPortfolioOpt matched to 5.7e-5.

## 6. Database (LOCKED schema, plus build rules)

Apply `sentinel-schema.sql` as the initial migration, unchanged in
structure: `securities`, `price_history`, `corporate_actions`,
`analyses`, `analysis_results`, `presets`. Rules:

- `NUMERIC` for all prices/weights (never float), `DATE` for market
  days, JSONB for inputs/metrics.
- `analyses` has **no identity columns** and never will. `slug` is a
  short random token (≥6 chars, base62) for share URLs `/a/<slug>`.
- Share links (DEFAULT): **DB slugs** (the schema's design), not
  weights-in-URL: links stay short and results cache by hash.
- Price depth (DEFAULT): cache **maximum available history** per
  security (the source reaches back decades); the analyzer defaults to
  a 10-year window and says so.
- Data source (DEFAULT): Yahoo Finance, behind a `PriceSource`
  interface with one implementation in v1, so a second source can be
  added without touching ingestion logic.
- Presets (DEFAULT): DB rows (schema already provides the table);
  seed with `60-40` (SPY/BND 60/40) and `k5-sample` (MCK/LLY/PWR/NVDA/
  STX at the K5 weights).
- Ingestion: a security row is created on first request for an unknown
  ticker (validate it exists at the source *before* creating; unknown
  tickers get a clean error, never a row). Nightly job refreshes every
  tracked security: new `price_history` rows (adjusted + raw OHLCV)
  and `corporate_actions` (splits/dividends). Adjusted close is what
  returns are built from.
- The results cache is keyed `(input_hash, data_asof)`; a nightly
  refresh simply makes new keys; old rows are never mutated.

## 7. Pages and routes

| Route | Page | Mockup |
|---|---|---|
| `/` | Landing: hero with growth chart card, tool grid, preset examples | `index.html` |
| `/analyze` | Analyzer (dashboard): input form + full results | `dashboard.html` |
| `/risk` | RiskLens report for the current analysis | `risk.html` |
| `/optimize` | Optimizer: method picker, frontier, weights table | `optimize.html` |
| `/tools` | Tool gallery: one card per tool in §8 | `tools.html` |
| `/tools/<slug>` | Individual tool page (form + signature visual + table) | per §8 |
| `/a/<slug>` | Shared analysis (read-only render of a stored analysis) | = `/analyze` results |
| `/api/tickers?q=` | Ticker autocomplete (from `securities` + source lookup) | n/a |
| `/api/analyze` | POST analysis input → JSON metrics + chart payloads | n/a |

**Portfolio input form (shared component, used by Analyzer and tools):**
dynamic rows of (ticker, weight %); add/remove row; benchmark selector
(default SPY); start-date selector (default 10y); **validation:**
1-25 holdings; tickers must resolve; weights must be ≥ 0 and sum to
100 ± 0.5 (offer one-click Normalize); duplicate tickers merge with a
notice. Errors are inline, specific, and never a stack trace.

**Analyzer results sections (in mockup order):** KPI cards (CAGR, vol,
Sharpe, max DD, end value) → growth line vs benchmark (log toggle) →
drawdown area → performance summary table (Portfolio vs Benchmark,
PV layout) → annual bars → monthly heatmap → allocation donut →
correlation heatmap → efficient frontier with "your portfolio" dot →
regime badge. **Risk page:** current VaR/ES (95/99), return histogram
with VaR line, Basel traffic light, Kupiec/Christoffersen/joint table,
tail diagnostics, regime panel. **Young-history states are designed:**
when history is short, panels render with the one-line explanation
(e.g. "backtests need 250+ observations") instead of NaNs or blanks:
mirror portlab's RiskLens behavior.

## 8. Tool inventory (19, every one with its signature visual)

Build order within §12 milestones. "PV" = Portfolio Visualizer also has
it; "ours" = Sentinel-only differentiator.

| # | Tool | Route | Engine | Signature visual | PV? |
|---|---|---|---|---|---|
| 1 | Backtest | /tools/backtest | backtest, metrics | Growth + drawdown + monthly heatmap | Yes |
| 2 | RiskLens report | /risk | risk.* | Return histogram + VaR line, traffic light | ours |
| 3 | Optimization | /optimize | optimize | Efficient frontier + portfolio dot | Yes |
| 4 | Monte Carlo | /tools/monte-carlo | montecarlo | Percentile fan chart | Yes |
| 5 | Financial goals | /tools/goals | montecarlo | Projection fan vs goal line | Yes |
| 6 | Factor analysis | /tools/factors | factor | Diverging exposure bars | Yes |
| 7 | Tactical allocation | /tools/tactical | tactical, indicators | Price vs MA signal chart | Yes |
| 8 | Rolling optimization | /tools/rolling-optimization | optimize, mpo | Stacked rolling-weights area | Yes |
| 9 | Rolling metrics | /tools/rolling-metrics | metrics, risk.var | Rolling Sharpe/vol lines | Yes |
| 10 | Asset-liability | /tools/alm | alm | Assets vs liabilities + funded ratio | ours |
| 11 | Options | /tools/options | derivatives | Payoff diagram | ours |
| 12 | Technical analysis | /tools/technical | indicators | Price + Bollinger, RSI/MACD panels | ours |
| 13 | Forecast | /tools/forecast | forecast | Forecast fan (widening cone) | ours |
| 14 | Stress testing | /tools/stress | stress, scenarios | Scenario P&L bars | ours |
| 15 | Attribution | /tools/attribution | attribution | Brinson waterfall | ours |
| 16 | Risk parity | /tools/risk-parity | optimize | Risk-contribution bars | Yes |
| 17 | Tax-aware | /tools/tax | taxlots, taxopt | After-tax vs pre-tax growth lines | ours |
| 18 | Correlations | /tools/correlations | covariance | Correlation heatmap matrix | Yes |
| 19 | Drawdown analysis | /tools/drawdowns | metrics, analytics | Drawdown area + episode table | Yes |

Each tool page = shared input form (prefilled from the visitor's current
analysis where sensible) + signature chart + results table + a one-line
"what this is" caption. No tool may ship as table-only.

## 9. Chart data contracts

Server returns JSON; ECharts renders. Common envelope:
`{"chart": "<type>", "title": ..., "series": [...], "meta": {"asof": ...}}`.
Required payloads: growth (dates, portfolio, benchmark), drawdown
(dates, dd%, deepest-point annotation), annual bars (years, %),
monthly heatmap (years × months %, annual column), frontier (risk/return
points + current-portfolio point), donut (label, weight), correlation
(labels, matrix), histogram (bins, counts, var_line), fan (dates, p5/
p25/median/p75/p95), waterfall (labels, deltas, cumulative), bars
(labels, values, colors by sign). **Every chart: hover tooltip with exact
values, axis labels, and the shared data-vintage label.** Static images
are not acceptable anywhere.

## 10. Validation, errors, edge cases

- Unknown ticker → inline error naming the ticker; nothing is stored.
- Weights sum outside 100 ± 0.5 → block with the actual sum shown +
  Normalize button.
- Security with < 60 trading days of history → analysis proceeds with
  the young-history panels (§7), never a crash.
- Delisted/no recent data → security page note; analysis excludes with
  a visible warning listing what was dropped and weights renormalized
  **only** after telling the visitor.
- All engine exceptions surface as a friendly error panel with a
  reference code; tracebacks go to logs only.
- Slugs are unguessable (random), analyses are public-by-link by
  design, and the UI says so next to the Share button ("anyone with
  this link can view these tickers and weights").

## 11. Deployment (DEFAULT)

Single small VM or container host: Django (gunicorn) + PostgreSQL +
nightly `refresh_prices` cron. portlab installs from its public repo
at a pinned version; no deploy keys or private tokens are involved.
Environment via `.env` (DB URL, secret key, data source settings).
HTTPS via the platform's standard terminator.
Nightly job logs to a table or file the admin can inspect; a failed
refresh must not take the site down (yesterday's cache keeps serving,
vintage label shows the stale date).

## 12. Milestones (execute in order; stop for owner review at each gate)

- **M0: Scaffold + data layer.** Repo layout §4, Django project, schema
  migrated, `PriceSource` + nightly refresh working for a seed universe
  (the 12 tickers in `docs/design/snippets/metrics.json` context: SPY,
  QQQ, BND, AAPL, MSFT, IWM, GLD, MCK, LLY, PWR, NVDA, STX), admin
  enabled. *Gate: `pytest` green; a page lists securities with price
  counts and latest dates.*
- **M1: Analyzer core.** Input form + validation, engine adapter,
  results cache, Analyzer page with all §7 sections and interactive
  charts, share links `/a/<slug>`, presets seeded. *Gate: golden test:
  the K5 preset reproduces `snippets/metrics.json` values within
  tolerance; SPY anchors (§5.6) pass.*
- **M2: RiskLens + backtests.** `/risk` complete: VaR/ES family,
  histogram + VaR line, traffic light, Kupiec/Christoffersen/joint
  (nullable-exceptions handling per §5.3), tail diagnostics, regime,
  young-history states. *Gate: SPY backtest anchors (§5.6) reproduced
  through the web stack.*
- **M3: Optimizer.** `/optimize`: method picker (max-Sharpe, GMV,
  risk parity, min-CVaR, BL), frontier + dot, weights table, rolling
  optimization + risk parity tool pages. *Gate: max-Sharpe weights
  match a direct portlab call to 1e-4.*
- **M4: Remaining tools.** Tools 1, 4-19 of §8, gallery page, each
  with signature visual + table. **No phasing (per the 2026-10-16
  §5 amendment):** the pinned portlab release covers every engine
  module, so all remaining tools build in this milestone, including
  Monte Carlo, goals, factors, tactical, rolling optimization, ALM,
  options, technical, forecast, stress, tax, and drawdown episodes.
  No gallery card is marked "coming later". *Gate: every card leads
  to a working page; screenshot pass vs `shots/`.*
- **M5: Hardening + deploy.** Error/edge pass (§10), cache behavior
  under refresh, deploy per §11, README with run/deploy instructions.
  *Gate: owner walkthrough on the deployed URL.*

## 13. Testing requirements

- Adapter unit tests: every engine call in §5's map exercised against
  portlab directly on fixed real-data fixtures (prices CSV in
  `tests/fixtures/`), tolerances stated per test.
- Golden numbers: `docs/design/snippets/metrics.json` (mock dataset)
  and the SPY anchors (§5.6) as regression tests: a red golden test
  means the build changed a number, which is a stop-and-report event.
- Page smoke tests: every route in §7/§8 returns 200 with its chart
  payload present, for the K5 preset.
- No test may assert a number nobody can re-derive: every expected
  value cites its source (fixture, hand formula, or anchor) in a
  comment.

## 14. Working protocol for Bob (owner's standing rules)

1. **Plan before code** (Planner mode): for each milestone, present the
   step list and wait for the owner's go-ahead in chat.
2. **Atomic steps** (Coder mode): one coherent change at a time; run
   the relevant tests after each; a failing test stops the line.
3. **Review like an auditor** (Reviewer mode): at each gate, report
   what was verified, with numbers, not "done."
4. **Commits** are authored `Ibrahim Oyeyinka
   <ibrahimoyeyinka@yahoo.com>`, small and descriptive.
5. **Never push without the owner's explicit "Push"** in that moment.
   A timed-out or ambiguous approval is a no.
6. **Never** add login/accounts/brokerage features, never commit
   portlab source, never put synthetic data in a production path,
   never silence a failing golden test by editing the expected value.
7. When a spec item and the code disagree, stop and ask; do not
   improvise around a LOCKED item.

---

*End of spec. Companion design package is the visual and database
contract; this document is the build contract. Conflicts: LOCKED items
in this spec win, then VISUAL-SPEC.md, then the mockups.*
