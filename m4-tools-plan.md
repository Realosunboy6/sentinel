# M4 remaining tools plan

Owner go-ahead: 2026-10-20. This milestone follows §8 and §12 of
`SENTINEL-BUILD-SPEC.md`; M0–M3 repair gate remains recorded in
`docs/repair-acceptance.md`. No push is authorized by the M4 go-ahead.

1. Build `/tools` with all 19 cards in inventory order and live routes.
   Preserve the visual specification and use its signature previews.
2. Use one shared portfolio input and cached adjusted-price loader on
   tool pages. Keep portlab imports inside the engine adapter. Validate
   tool-specific parameters and show honest short-history states.
3. Implement the return/history tools: backtest, rolling metrics,
   correlations and drawdowns. Keep existing RiskLens, optimization,
   rolling optimization and risk parity routes connected.
4. Implement simulations and allocation tools: Monte Carlo, goals,
   factors, tactical allocation and ALM.
5. Implement the remaining tools: options, technical, forecast, stress,
   attribution and tax. Each has its signature visual, results table,
   and one-line explanation.
6. Exercise every portlab adapter on fixed real-price fixtures, smoke
   every route with cached K5 data, run golden regressions, and compare
   desktop/mobile screenshots with `docs/design/shots/tools.png`.
   Stop for owner review after the local M4 gate; push only after an
   explicit `Push` message.

## Current gate evidence (2026-10-21)

- All 19 gallery cards resolve. The 15 new reports render charts and
  result tables from the committed K5 adjusted-price fixture; 22 M4
  tests pass, including numeric backtest, simulation, correlation and
  drawdown comparisons to direct portlab calls.
- Full SQLite suite passed with one PostgreSQL-only row-lock skip.
  `manage.py check`, `makemigrations --check --dry-run`, and
  `git diff --check` passed. The desktop gallery screenshot has 19
  populated cards and follows the locked three-column mockup.
- The PostgreSQL test server could not start on this host:
  `pg_ctl.exe` failed with Windows `Illegal System DLL Relocation`.
  PostgreSQL and narrow-screen screenshot gates remain open.
- Scope limits: factor analysis provides benchmark market beta, because
  no dated multi-factor return series is cached. Attribution compares
  entered holdings against their equal-weight basket, because there is
  no benchmark constituent map. The tax page models one assumed lot per
  holding and liquidation taxes; it identifies harvest candidates but
  does not run the full tax-weight optimizer in a web request (a local
  K5 probe took roughly 15 minutes). These assumptions are displayed
  on their report pages. Do not call this an unqualified M4 acceptance.
