# M3 gate: optimizer

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
- Shared options form and current-analysis selection, with links back to the
  Analyzer to change tickers or starting weights. All M3 calculations use
  cached adjusted prices and preserve the selected analysis's date range.

## Evidence

- Full suite: **129 passed in 69.70 seconds**, including **27 new M3 tests**.
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

M3 is ready for owner review. It is committed locally and has not been pushed.
