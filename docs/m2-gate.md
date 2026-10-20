# M2 gate: RiskLens

> **Repair follow-up (2026-10-19):** the findings below describe the pre-repair state. See [current acceptance evidence](repair-acceptance.md) for fixes, regression tests and remaining limits.

**Acceptance note (2026-10-18):** the numerical gate below passed. A later
contract review found a missing deepest-point annotation required by section 9.
That follow-up was fixed and verified on 2026-10-19. See
[build-contract review](build-contract-audit.md).

Verified locally on 2026-10-18 with Python 3.14, Django 5.2.18,
portlab 0.2.2, and an isolated SQLite test database.

## Validation

- Full suite: **102 passed in 83.75 seconds**, including 15 new M2 tests.
- `python manage.py check`: no issues.
- Existing M1 golden expectations and committed price fixtures were unchanged.
- SPY fixture loaded into `PriceHistory`, then requested through `/risk`:
  1,703 scored days, 86 exceptions, Kupiec LR within 0.001 of 0.009,
  Christoffersen counts 1542/74/74/12, LR within 0.00001 of 10.589773,
  and joint LR within 0.001 of 10.5987.
- K5 route returns 200 with histogram, regime, and drawdown payloads, using
  the stored analysis end date. Requests read cached prices only.
- Short histories render explanatory states; missing prices/engine produce
  503; unknown analysis slugs produce 404. Reports serialize without NaN.
- Desktop browser inspection of a rendered K5 fixture preview confirmed the
  histogram, both VaR markers, drawdown, regime bars, and report tables render.
  This was a generated preview, not a production deployment or mobile QA pass.

## Corrections and conventions

- Likelihood-ratio backtests use 95% rolling-250 historical VaR over all scored
  observations. The nullable exception series goes directly to the engine tests.
- The Basel light separately scores **99%** historical VaR over the latest
  **250 scored days**. K5 fixture result: green, one exception.
- Regime estimates use portlab's actual `calm_var`/`stressed_var` fields and
  map its numeric labels to Calm/Stressed. Missing regimes remain unavailable.
- Hill receives losses `-returns`, rather than absolute returns combining
  both tails. Jarque-Bera is unavailable below eight observations.
- GARCH failures remain unavailable; historical VaR is never relabeled GARCH.
- Only final unconditional forecasts and the latest trailing GARCH window are
  fitted for display. Final-window equivalence to expanding forecasts is tested.
  Backtests still use the complete rolling forecast series.
- Histogram markers use a numeric return axis, avoiding unmatched category labels.
- Risk navigation preserves the selected analysis through the session.
- Historical stress rows replay observed constant-mix portfolio returns over
  explicitly dated COVID and 2022 episodes. Missing episodes remain unavailable.
  No rate shock or volatility scenario is invented from the mockup's numbers.

## Handoff

M2 is ready for owner review. M3 optimizer, M4 remaining tools, and M5 deployment
remain. This gate does not certify every pre-existing M1 path against the full
build specification. No deployment or GitHub push was performed.
