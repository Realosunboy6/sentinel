# M3 gate: optimizer

> **Repair follow-up (2026-10-19):** the findings below describe the pre-repair state. See [current acceptance evidence](repair-acceptance.md) for fixes, regression tests and remaining limits.

**Acceptance follow-up (2026-10-19):** the missing shared editable portfolio
form, engine-error references, and visual-review follow-ups are now implemented
and checked. M3 is ready for owner review. PostgreSQL/Python 3.12 coverage and
inherited schema differences remain open. See
[build-contract review](build-contract-audit.md) and
[visual comparison](visual-review-m2-m3.md).

Verified locally on 2026-10-18 with Python 3.14, Django 5.2.18,
portlab 0.2.2 and isolated SQLite databases. M2 commit 7b560aa was pushed
and verified on GitHub before M3 began.

## Delivered

- `/optimize`: max-Sharpe, GMV, risk parity, minimum CVaR,
  Black-Litterman, and an additional turnover-aware mean-variance choice.
- `/tools/risk-parity`: current/optimized fractional risk contributions,
  allocation changes, comparative statistics and the frontier.
- `/tools/rolling-optimization`: historical rolling targets as a stacked
  interactive area chart and dated allocations with turnover/cost estimates.
- The same editable portfolio form is now used by Analyzer and all M3 pages,
  prefilled from the selected analysis. Tool edits recalculate temporarily
  without overwriting the saved report. M3 calculations use cached adjusted
  prices and the entered date range; initial values preserve the saved range.

## Evidence

- Latest full suite: **144 passed in 120.06 seconds**, including **42 M3 tests**.
- Django system check: no issues. `git diff --check`: no whitespace errors.
- Adapter max-Sharpe weights match a direct public portlab call within the
  required absolute **1e-4** tolerance. The database/web route meets the same
  tolerance against a direct call on the actual cached returns.
- The other five methods also match direct portlab calls, with absolute
  weight tolerance 1e-6 on the committed K5 fixture.
- Tests verify feasible weight caps, weights summing to one, frontier target
  feasibility, comparable return bases, risk-contribution totals, CVaR
  confidence convention, turnover and cost units, invalid options and views,
  missing engine/data/analysis states, and young-history handling.
- Changing returns on/after a rolling decision does not change that date's
  target. Training end dates precede decision dates. Subsequent turnover is
  checked against the independently drifted previous allocation.
- Live local Django browser inspection used a separate SQLite database seeded
  from the committed real K5 fixture. Frontier, portfolio dots, grouped risk
  bars, stacked rolling weights and tables rendered. Submitting an explicit
  Black-Litterman view recalculated the allocation successfully.
- Responsive check at a 390px viewport: optimizer and rolling pages stay
  within the viewport (document width 375px with scrollbar); fields and
  charts stack; wide tables scroll within their containers. The initial chart
  grid overflow was fixed. The viewport override was reset afterward.
- Existing M1 golden values and M2 SPY anchors passed without modification.
- New checks verify edited holdings/dates on each M3 page, no saved-analysis
  mutation or source fetch, calculations without an existing analysis,
  duplicate notices, invalid weights/dates/tickers, safe log-correlated
  engine references and the deepest-drawdown marker.

## Numerical conventions

Default bounds are [0, 0.5], full investment, no shorts. Default risk-free rate
is zero. Mean-variance inputs are annualized arithmetic means and Ledoit-Wolf
covariance. Bounded mean-variance solves explicitly use SLSQP for reproducibility.
The adapter checks finite weights, budget and bounds before displaying a result.

The public portlab `frontier()` extends its sweep to the largest individual
asset mean, which can be infeasible under a cap. M3 instead uses public
`min_vol_at_return()` calls over feasible targets from GMV to the capped
maximum-return allocation, and checks each achieved target. No portlab source
was copied or altered.

Black-Litterman uses the entered portfolio as an explicitly labeled reference
prior, not market-cap weights. Absolute annual return views and confidences
come from the visitor. Defaults: risk aversion 2.5 and tau 0.05. Both current
and optimized expected returns use the same posterior when this method is
selected. Historical daily CVaR still uses observed returns and confidence 0.95.

Turnover is half the L1 weight change. Estimated transaction cost applies
the entered bps to the full L1 traded notional. Only the explicitly named
turnover-aware method includes this cost in its optimization objective,
using portlab's `opt_constrained` with risk aversion 5. Other methods report
the estimated cost after optimization. Taxes and market impact are excluded.

Rolling defaults: 252 prior observations and decisions every 21 observations.
Each training sample excludes the decision date's return. Previous targets
drift through observed asset returns before the next turnover comparison.
The first comparison uses the visitor's entered weights. The chart is an
allocation study, not a strategy performance backtest.

## Limits and handoff

This gate establishes regression agreement with the pinned engine and input
feasibility checks, not an independent certificate of global optimality for
every optimizer. Estimates are in-sample; no future-performance claim is made.
Browser checks cover the local fixture app, not a production deployment or
exhaustive device matrix. No new schema migrations or external market requests
were needed. M4 remaining tools/gallery and M5 hardening/deployment remain.

M3 and its acceptance follow-ups are local changes awaiting owner review;
they have not been pushed. The tracked implementation gaps are closed, while
environment verification and inherited schema reconciliation remain explicit
limitations rather than passed checks.
