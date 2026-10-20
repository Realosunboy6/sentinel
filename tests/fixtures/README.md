# tests/fixtures — Price data fixtures

These CSV files contain real historical adjusted-close prices downloaded
from Yahoo Finance via `yfinance`.  They are committed once and used as
fixed regression anchors.

## Files

### k5_prices.csv
- **Tickers:** LLY, MCK, NVDA, PWR, SPY, STX (K5 portfolio + SPY benchmark)
- **Date range:** 2021-01-04 to 2026-10-16 (1,454 trading days, after dropna)
- **Column:** `adj_close` (adjusted close, Yahoo Finance)
- **Source:** Yahoo Finance via `yfinance.download(..., auto_adjust=False)`
- **Download date:** 2026-10-16
- **Use:** Golden-number regression test (`tests/test_golden.py`) against
  `tests/fixtures/k5_golden.json` (repository-recorded ruling 2026-10-16; the design snippet is illustrative)

### spy_prices.csv
- **Ticker:** SPY
- **Date range:** 1993-01-29 to 2026-10-16 (8,487 trading days)
- **Column:** `adj_close` (adjusted close, Yahoo Finance)
- **Source:** Yahoo Finance via `yfinance.download(..., auto_adjust=False)`
- **Download date:** 2026-10-16
- **Use:** SPY VaR anchor test (`tests/test_spy_anchors.py`) against the
  verified anchors in spec §5.6

## Stop-and-report rule (spec §13, LOCKED)

Yahoo Finance retroactively restates adjusted-close history (dividend
retroactive adjustments, splits).  If a golden test ever fails by a small
amount, **data vintage is the first suspect**.

**Do not edit expected values to silence a failing test.**
Stop and report: which test failed, what value was produced, what was expected,
and the delta.  Then investigate whether the fixture is stale before touching
any expected value in any test file.

## Column name
Both files use the column name `SPY`, `MCK`, etc. — the ticker symbol as returned
by yfinance.  The test helpers access the column by name.
