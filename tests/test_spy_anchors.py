"""
SPY VaR backtest anchor tests (spec §5.6, verified anchors).

Construction:
  - Fixture:   tests/fixtures/spy_prices.csv  (committed adj-close, full SPY history)
  - Window:    returns starting 2019-01-10 (total 1,953 rows, 250-day warmup → 1,703 scored days)
  - VaR:       rolling-250-day historical VaR, alpha=0.05
  - Backtest:  portlab.risk.backtest functions (exceptions, kupiec_pof, christoffersen_ind, joint_test)

Verified anchors (spec §5.6):
  - 1,703 scored days
  - 86 exceptions
  - Kupiec LR 0.009   (exact: 0.00890)
  - Christoffersen counts: 1542 / 74 / 74 / 12
  - LR_ind 10.589773
  - Joint LR 10.5987

These numbers were confirmed by running portlab 0.2.2 on the committed fixture
(2026-10-16) and match the spec values to the precision stated.

STOP-AND-REPORT RULE (LOCKED per spec §13):
  If any assertion fails, do not change the expected value.
  Stop and report: test name, produced value, expected value, delta.

Notes on nullable-boolean handling (spec §5.3):
  - exceptions() returns a nullable-boolean Series (True/False/<NA>)
  - Do NOT dropna() before christoffersen_ind  (it re-joins gaps)
  - Do NOT .astype(bool) (raises on <NA>)
  - Fill with False ONLY for display copies, never for the test calls
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# The start date that yields exactly 1,703 scored days (spec §5.6)
SPY_BACKTEST_START = "2019-01-10"


@pytest.fixture(scope="module")
def spy_backtest():
    """
    Returns (exc_series, kupiec_result, chris_result, joint_result, n_scored, n_exc).
    exc_series is the raw nullable-boolean Series from portlab.risk.backtest.exceptions().
    """
    import portlab.risk.var as pl_var
    import portlab.risk.backtest as pl_bt

    df = pd.read_csv(FIXTURES / "spy_prices.csv", index_col="date", parse_dates=True)
    df.index = pd.to_datetime(df.index)
    returns_full = df["SPY"].pct_change().dropna()
    returns = returns_full[returns_full.index >= SPY_BACKTEST_START]

    var_series = pl_var.historical_var(returns, alpha=0.05, window=250)
    exc = pl_bt.exceptions(returns, var_series)

    # Count scored days: non-NA entries in exc
    scored = exc.dropna()
    n_scored = len(scored)
    n_exc = int(scored.sum())

    # Pass exc directly (not dropna'd, not .astype(bool) — spec §5.3)
    kup   = pl_bt.kupiec_pof(exc, alpha=0.05)
    chris = pl_bt.christoffersen_ind(exc)
    joint = pl_bt.joint_test(exc, alpha=0.05)

    return exc, kup, chris, joint, n_scored, n_exc


# ---------------------------------------------------------------------------
# Scored-day and exception counts
# Source: spec §5.6 — "1,703 scored days, 86 exceptions"
# ---------------------------------------------------------------------------

def test_scored_day_count(spy_backtest):
    # Source: spec §5.6
    _, _, _, _, n_scored, _ = spy_backtest
    assert n_scored == 1703

def test_exception_count(spy_backtest):
    # Source: spec §5.6
    _, _, _, _, _, n_exc = spy_backtest
    assert n_exc == 86


# ---------------------------------------------------------------------------
# Kupiec POF test
# Source: spec §5.6 — "Kupiec LR 0.009"
# Exact value from portlab on fixture: 0.00890359
# ---------------------------------------------------------------------------

def test_kupiec_lr(spy_backtest):
    # Source: spec §5.6 (stated as 0.009); exact portlab output: 0.00890
    _, kup, _, _, _, _ = spy_backtest
    assert kup["lr_stat"] == pytest.approx(0.009, abs=5e-4)

def test_kupiec_not_rejected(spy_backtest):
    # H0: exception rate == alpha — should NOT be rejected at 5%
    _, kup, _, _, _, _ = spy_backtest
    assert kup["p_value"] > 0.05


# ---------------------------------------------------------------------------
# Christoffersen independence test
# Source: spec §5.6 — "counts 1542/74/74/12, LR_ind 10.589773"
# ---------------------------------------------------------------------------

def test_christoffersen_counts(spy_backtest):
    # Source: spec §5.6
    _, _, chris, _, _, _ = spy_backtest
    assert chris["n00"] == 1542
    assert chris["n01"] == 74
    assert chris["n10"] == 74
    assert chris["n11"] == 12

def test_christoffersen_lr_ind(spy_backtest):
    # Source: spec §5.6 — "LR_ind 10.589773"
    _, _, chris, _, _, _ = spy_backtest
    assert chris["lr_stat"] == pytest.approx(10.589773, rel=1e-4)


# ---------------------------------------------------------------------------
# Joint test (correct conditional coverage)
# Source: spec §5.6 — "joint LR 10.5987"
# ---------------------------------------------------------------------------

def test_joint_lr(spy_backtest):
    # Source: spec §5.6 — "joint LR 10.5987"
    _, _, _, joint, _, _ = spy_backtest
    assert joint["lr_stat"] == pytest.approx(10.5987, rel=1e-4)


# ---------------------------------------------------------------------------
# Nullable-boolean handling guard (spec §5.3)
# exc must be a nullable-boolean Series, not bool or float
# ---------------------------------------------------------------------------

def test_exceptions_series_is_nullable(spy_backtest):
    exc, _, _, _, _, _ = spy_backtest
    # Must contain pd.NA, not float NaN — verifying spec §5.3 is honoured
    import pandas as pd
    # At least some warmup NAs must exist
    assert exc.isna().any(), "exceptions() should have <NA> in warmup period"
    # Must NOT be plain bool dtype (which would raise on <NA>)
    assert str(exc.dtype) in ("boolean", "object"), (
        f"exceptions() dtype should be nullable boolean, got {exc.dtype}"
    )
