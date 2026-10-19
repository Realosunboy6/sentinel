# M2/M3 manual visual review, 2026-10-19

References: `docs/design/optimize.html`, `risk.html`, `VISUAL-SPEC.md`, and
the committed `shots/optimize.png` and RiskLens design package. Checked the
local Django fixture app in the browser, including a 1280px viewport to compare
the optimizer layout with the reference width, and a 390px phone viewport.

This is a manual design comparison, not an automated pixel-difference test.
The pages are not claimed to be pixel-identical to static illustrative mockups.

| Contract element | Implementation / observation |
|---|---|
| Navy navigation, pale page background, white cards, 10px radii, light borders | Existing base template and shared design stylesheet retained |
| System typography and tabular numerical tables | Shared stylesheet retained; percentage inputs now seed clean decimal values |
| Frontier beside risk-contribution panel on desktop | Same two-panel order and wider-left layout; single-column on phone |
| Horizontal risk-contribution bars in optimizer reference | Corrected from vertical bars; navy current and emerald optimized bars, explicit legend |
| Frontier and current portfolio marker | Interactive line and portfolio marker retained; optimized allocation adds a labeled diamond series |
| Portfolio input component in spec sections 7-8 | Shared editable rows, Normalize, benchmark and date controls now appear above results on Analyzer and M3 tools |
| Current-versus-optimized comparison and allocations | Tables retain the reference's card/table styling; selected method determines optimized column |
| Risk histogram, VaR markers and traffic light | Existing real-engine panels retained; no mockup values substituted |
| Risk drawdown and regime panels | Both present; actual deepest drawdown now has a visible dot and value label |
| Data vintage and chart tooltips | Payloads retain vintage metadata; results show the selected history; charts retain interactive tooltips |
| Rolling target allocation visual | Stacked step-area chart retained, with design-palette colors and dated allocation table |
| 390px editor and chart layout | Five prefilled rows and date controls fit; document width 375px within 390px viewport with scrollbar; wide result tables use local horizontal scrolling |

Browser interactions exercised add asset, edit its ticker/weight, Normalize,
remove asset, renormalize and submit optimization. The result page rendered
successfully. Browser inspection confirmed correctly formatted initial weights
29.98, 23.55, 19.06, 15.61 and 11.8. The updated drawdown minimum label was
visible on the RiskLens chart. Temporary viewport overrides were reset.

The Analyzer's actual shared-editor submission also completed and redirected
to a saved K5 report in the isolated fixture database, checking the browser
form-to-server path in addition to the mocked M1 POST regression test.

## Scope differences from the static optimizer mockup

- The required input form and method picker add page height; the static mockup
  starts with illustrative charts. The build specification takes precedence.
- Current/optimized risk contributions are compared rather than displaying
  only one illustrative allocation. Values come from cached real returns.
- The comparison table uses current versus the selected method, supporting all
  required methods, instead of a fixed current/Max-Sharpe/risk-parity trio.
- The mockup's Monte Carlo panel belongs to M4 under the milestone inventory.
- The inherited base navigation remains the project's existing implementation;
  this review does not claim exact chrome dimensions against every reference.

Owner visual acceptance remains a milestone review step. No new framework,
bundler, production data source, database schema or engine implementation was
introduced for this visual work.
