# M3: Optimizer

Authorized by the owner's 2026-10-18 instruction: "push AND START M3".
M2 commit 7b560aa was pushed and verified on GitHub before starting.

## Steps

1. Add lazy portlab adapter calls for max-Sharpe, GMV, equal risk
   contribution, min-CVaR, and Black-Litterman with explicit absolute views.
   Include portlab's turnover-penalized mean-variance method as a clearly
   named additional choice. Default long-only, 50% cap, rf=0, annualized
   arithmetic means and Ledoit-Wolf covariance. Validate returned feasibility.
2. Build `/optimize` for the selected analysis, cached prices only, preserved
   dates, validated options, frontier/current/optimized dots, weights and risk
   contributions, comparable statistics, turnover and cost estimates.
3. Add `/tools/risk-parity` and `/tools/rolling-optimization`, linked from the
   optimizer. Rolling targets use only observations strictly before each date;
   show stacked weights, dated allocations, and turnover. No performance claim.
4. Add real-fixture adapter and database/web tests; max-Sharpe must match the
   same direct portlab call to 1e-4. Test constraints, invalid inputs, short
   history, missing prices/engine, Black-Litterman views and no look-ahead.
5. Run all existing and new tests, Django checks, desktop/mobile browser
   inspection, record gate evidence, commit locally and stop for owner review.

## Numerical details

- Black-Litterman reference weights are the entered portfolio, explicitly
  labeled a user reference prior, not market-cap weights. Views are supplied
  by the visitor, never inferred or invented.
- Use `solver="slsqp"` for reproducible bounded mean-variance solves. The
  library's `frontier()` sweeps to `mu.max()` even under a cap; instead call
  its public `min_vol_at_return()` on feasible targets ending at the capped
  maximum-return allocation. Do not display infeasible solver outputs.
- CVaR confidence is 0.95, not risk.var's tail probability 0.05.
- Turnover = half the L1 change in weights. Display round-trip traded
  notional and proportional cost consistently; tc_bps applies to the full L1
  traded notional as in portlab.opt_constrained.
- Rolling defaults: 252 prior observations, decisions every 21 observations.
  The decision date's return is excluded from estimation. Previous targets
  drift through realized asset returns before the next turnover calculation.
- Monte Carlo belongs to M4 despite its illustrative placement in the mockup.

## Status

- [x] Engine and adapter tests
- [x] Optimizer page
- [x] Risk-parity and rolling tools
- [x] Full tests and browser checks
- [x] Initial gate report and local commit
- [x] Reuse the shared editable portfolio input required by spec sections 7-8
- [x] Include a reference code on every engine-error panel
- [x] Complete a requirement-by-requirement visual review against reference designs
- [x] Close the identified implementation gaps (2026-10-19; 144 tests pass)
- [ ] Owner review before advancing to M4

The earlier checklist did not cover every cross-cutting requirement. The
numerical gate passed. The follow-up implementation work is now ready for
owner review; environment/schema coverage remains explicitly open. See
`docs/build-contract-audit.md` for the evidence and inherited schema issues.

Never push M3 without a new explicit instruction. No golden expectations or
fixture histories may be edited to silence failures.
