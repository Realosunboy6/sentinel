# M2: RiskLens + VaR Backtests — Plan

> **2026-10-19 repair follow-up:** use [repair acceptance](docs/repair-acceptance.md) for current evidence and [outline review](docs/plan-outline-review.md) for the original discrepancies. Numerical gates and full acceptance are reported separately. Owner review before M4 remains open.

## Top-Level Overview

**Goal:** Deliver the `/risk` page — a complete RiskLens report for the current analysis —
backed by the portlab risk engine and all §7 Risk page sections.

**Scope:**
- `apps/analysis/engine.py` — new `run_risklens()` function (VaR family, backtest, tail, regime)
- `apps/analysis/charts.py` — `histogram_chart()` and `regime_panel_chart()` payload serializers
- `apps/analysis/views.py` — `risk_view` at `GET /risk?slug=<slug>`
- `templates/analysis/risk.html` — full Risk page template matching `docs/design/risk.html`
- Young-history states for all panels that need ≥250 observations
- SPY anchor integration test through the web stack

**Gate (spec §12 M2):** SPY backtest anchors reproduced through the web stack; `/risk` returns 200
with all panel payloads for the K5 preset.

**Out of scope for M2:** `/optimize` page (M3), tool pages (M4).

---

## Sub-Task 1 — `run_risklens()` engine function

**Intent**
Add a second public function to `apps/analysis/engine.py` that computes the full RiskLens
report: the full VaR family (historical, parametric, parametric-t, Cornish-Fisher, GARCH),
the rolling-250 VaR backtest with all three tests (Kupiec, Christoffersen, joint), the Basel
traffic light, regime-conditional VaR, tail diagnostics, and young-history state flags.

**Expected Outcomes**
- `run_risklens(port_returns, tail_alpha=0.05) -> dict` exported from `engine.py`.
- Returns a dict with these keys:
  - `var_table`: list of dicts — one row per VaR method — each `{method, var95, var99, es95, es99}`.
    Methods: historical, parametric, parametric_t, cornish_fisher, garch.
  - `backtest`: `{n_scored, n_exceptions, kupiec_lr, kupiec_p, kupiec_reject,
      chris_n00, chris_n01, chris_n10, chris_n11, chris_lr, chris_p,
      joint_lr, joint_p, basel_zone, young_history}`.
    `young_history = True` when scored days < 250 (show the one-line explanation).
  - `regime`: `{current, calm_var95, stressed_var95, full_var95}` from `regime_var` and `ewma_vol`.
  - `tail`: `{skew, exkurt, jb_p, hill, worst_day, best_day}` (already in `run_analysis`;
    re-exposed here for the Risk page's standalone use).
  - `histogram`: `{bins, counts, var95_line, var99_line}` — pre-binned return distribution
    for ECharts bar chart.
  - `data_vintage`: `{start, end}`.
- Nullable-boolean handling (spec §5.3): `exceptions()` Series passed raw to all three
  backtest functions; never `dropna()`'d or `.astype(bool)`'d before those calls.
- `garch_var` default `mean="zero"`, `parametric_var` default `mean="constant"` (spec §5.4).
- VaR sign: always positive = loss (spec §5.2).

**Todo List**
1. Check exact portlab signatures for `parametric_var`, `parametric_var_t`,
   `cornish_fisher_var`, `garch_var`, `regime_var`, `ewma_vol`, `basel_traffic_light`.
2. Write `run_risklens()` in `apps/analysis/engine.py`.
3. Export it from the module (add to the module docstring list).

**Relevant Context**
- `apps/analysis/engine.py` — existing `run_analysis()` for patterns to follow.
- Spec §5.1–5.4 (alpha duality, VaR sign, exceptions handling, GARCH/parametric defaults).
- `tests/test_spy_anchors.py` — existing fixture + anchor numbers (window=250, start 2019-01-10).

**Status:** [x] complete (2026-10-18; see docs/m2-gate.md)

---

## Sub-Task 2 — Chart payload serializers for the Risk page

**Intent**
Add two new serializers to `apps/analysis/charts.py`:
- `histogram_chart()` — return distribution as a bar chart with the VaR 95/99 vertical lines
  (the Risk page's signature visual per spec §8).
- `regime_panel_chart()` — small bar chart showing calm vs stressed vs full-sample VaR 95%.

**Expected Outcomes**
- `histogram_chart(bins, counts, var95_line, var99_line, asof)` → `{"chart": "bar", ...}`
  with two markLine entries for VaR95 and VaR99 (red dashed lines).
  Bars left of VaR95 line colored `#dc2626`; bars right colored `#10233f`.
- `regime_panel_chart(calm_var95, stressed_var95, full_var95, asof)` → `{"chart": "bar", ...}`
  showing three bars with labels.
- Both include hover tooltips and data-vintage label (spec §9).

**Todo List**
1. Write `histogram_chart()` in `apps/analysis/charts.py`.
2. Write `regime_panel_chart()` in `apps/analysis/charts.py`.

**Relevant Context**
- `apps/analysis/charts.py` — existing serializer patterns.
- `docs/design/risk.html` — visual reference for the histogram and regime panel.
- `docs/design/snippets/histogram.svg` — histogram shape reference.
- Spec §9 (chart envelope format, tooltip requirement).

**Status:** [x] complete (2026-10-18; see docs/m2-gate.md)

---

## Sub-Task 3 — `/risk` view and template

**Intent**
Build the `/risk` page end-to-end. It is reached via `GET /risk?slug=<slug>` — the slug
identifies the analysis whose portfolio is being examined. The saved report remains shareable; its shared portfolio editor can create a new analysis. It it loads the stored `AnalysisResult`, re-runs `run_risklens()` on the portfolio
returns derived from `price_history`, and renders all sections.

**Expected Outcomes**
- `GET /risk?slug=<slug>` → 200 with all Risk page sections rendered.
- Sections in mockup order (spec §7 / `risk.html`):
  1. KPI cards: VaR95, VaR99, ES95/ES99, Basel traffic light zone, plus the shared editable input.
  2. Return histogram + VaR95/99 lines (signature visual).
  3. Two-column: Drawdown area | Regime panel (current regime badge + calm/stressed table).
  4. Two-column: Tail diagnostics table | Stress scenarios table (from `run_risklens()`).
  5. Kupiec / Christoffersen / joint backtest table.
- Young-history state: if `backtest.young_history == True`, the backtest panel renders
  "Backtests need 250+ scored observations" instead of the table. Other panels still render.
- Engine-unavailable → `engine_unavailable.html` (same pattern as M1).
- Nav "Risk" link in `base.html` updated to point to `/risk` with the current slug if one
  exists in the session (or plain `/risk` if not).

**Todo List**
1. Add `risk_view` to `apps/analysis/views.py`.
2. Add `path("risk", risk_view, name="risk")` to `apps/analysis/urls.py`.
3. Write `templates/analysis/risk.html` extending `base.html`, matching `risk.html` mockup.
4. Update `templates/base.html` nav "Risk" link.
5. Write `apps/analysis/risklens.py` — thin orchestration layer that loads prices from
   `price_history`, builds returns, calls `run_risklens()`, and assembles chart payloads.
   (Mirrors `analyzer.py` for the Analyzer page.)

**Relevant Context**
- `apps/analysis/views.py` — `shared_analysis_view` pattern (load Analysis → AnalysisResult).
- `docs/design/risk.html` — full mockup (pixel reference).
- `docs/design/shots/risk.png` — rendered screenshot.
- Spec §7 (Risk page sections, young-history states).

**Status:** [x] complete (2026-10-18; see docs/m2-gate.md)

---

## Sub-Task 4 — SPY anchor integration test through the web stack

**Intent**
The M2 gate requires the SPY anchors to pass "through the web stack" — meaning via
`run_risklens()` called from the view layer, not just direct portlab calls. This also
validates the young-history logic and the backtest table rendering.

**Expected Outcomes**
- `tests/test_m2_risklens.py`:
  - `test_run_risklens_spy_anchors`: calls `run_risklens()` directly on the SPY fixture
    (window 2019-01-10 onwards, 250-day rolling), asserts the §5.6 anchor numbers.
  - `test_run_risklens_young_history`: calls `run_risklens()` on a short Series (< 500 rows),
    asserts `backtest.young_history == True`.
  - `test_run_risklens_var_sign`: asserts all var/es values are positive (spec §5.2).
  - `test_risk_page_200`: `GET /risk?slug=<slug>` → 200 (DB test, mocked risklens call).
  - `test_risk_page_contains_histogram`: response content includes `chart-histogram`.
  - `test_risk_page_young_history_message`: short-history analysis shows the explanation string.

**Todo List**
1. Write `tests/test_m2_risklens.py`.

**Relevant Context**
- `tests/test_spy_anchors.py` — existing anchor fixture and start-date logic.
- `tests/test_pages.py` — existing page-smoke patterns.

**Status:** [x] complete (2026-10-18; see docs/m2-gate.md)

---

## Sub-Task 5 — Full pytest gate

**Expected Outcomes**
- `pytest` exits 0 across all M0 + M1 + M2 tests.
- README M2 row marked ✅.
- Commit `M2: RiskLens + VaR backtests`.

**Status:** [x] complete (2026-10-18; see docs/m2-gate.md)

---

## Implementation Notes

- Sub-Tasks are strictly ordered (each depends on the previous).
- Commit format: `M2.N: <description>`.
- Author: `Ibrahim Oyeyinka <ibrahimoyeyinka@yahoo.com>`.
- Do not push until the owner says "Push".
- Stop-and-report rule applies to any anchor mismatch in ST4.
