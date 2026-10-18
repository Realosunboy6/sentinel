"""
portlab engine adapter — the ONLY module in this repo that imports portlab.

All analysis calls go through run_analysis().  The rest of the app never
touches portlab directly.

Alpha convention (spec §5.1)
----------------------------
- This module's public parameter is ``tail_alpha`` (a tail probability, e.g. 0.05).
- ``portlab.risk.var.*`` functions receive  ``alpha = tail_alpha``       (0.05)
- ``portlab.metrics.*`` functions receive   ``alpha = 1 - tail_alpha``   (0.95)
- The adapter converts at the boundary; callers never see this duality.

VaR sign convention (spec §5.2)
--------------------------------
portlab returns VaR as a *positive* number (= loss magnitude).
Returns are simple returns; positive = gain.  An exception day satisfies
``return < -VaR``.

portlab import (owner ruling)
------------------------------
Imported lazily *inside* run_analysis(), not at module load.  This ensures
the engine-unavailable error page can render even when portlab is absent.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TRADING_DAYS = 252  # annualisation constant


class EngineUnavailableError(Exception):
    """Raised when portlab cannot be imported or a fatal engine error occurs."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_analysis(
    holdings: list[dict],
    prices_df: pd.DataFrame,
    benchmark_returns: pd.Series,
    tail_alpha: float = 0.05,
) -> dict[str, Any]:
    """
    Run a full portfolio analysis.

    Parameters
    ----------
    holdings:
        [{"symbol": "MCK", "weight": 0.2998}, ...]  Weights must sum to 1.
    prices_df:
        Wide DataFrame of **simple returns** (not prices), one column per
        symbol, index = datetime.date, columns = symbols.
    benchmark_returns:
        pd.Series of benchmark simple returns aligned to the same index.
    tail_alpha:
        Tail probability for VaR/ES (default 0.05 → 95% confidence).

    Returns
    -------
    dict matching the shape documented in m1-analyzer-plan.md §ST1 and
    mirroring docs/design/snippets/metrics.json.
    """
    try:
        import portlab.metrics as pl_metrics
        import portlab.risk.var as pl_var
        import portlab.risk.tail as pl_tail
        import portlab.risk.regime as pl_regime
        import portlab.covariance as pl_cov
        import portlab.optimize as pl_opt
    except ImportError as exc:
        raise EngineUnavailableError(
            f"portlab is not importable: {exc}.  "
            "Install it with: pip install portlab[opt]==0.2.2"
        ) from exc

    try:
        return _run(
            holdings, prices_df, benchmark_returns, tail_alpha,
            pl_metrics, pl_var, pl_tail, pl_regime, pl_cov, pl_opt,
        )
    except EngineUnavailableError:
        raise
    except Exception as exc:
        logger.exception("engine.run_analysis failed")
        raise EngineUnavailableError(f"Engine error: {exc}") from exc


# ---------------------------------------------------------------------------
# Internal implementation
# ---------------------------------------------------------------------------

def _run(
    holdings, prices_df, benchmark_returns, tail_alpha,
    pl_metrics, pl_var, pl_tail, pl_regime, pl_cov, pl_opt,
):
    symbols = [h["symbol"] for h in holdings]
    raw_weights = np.array([h["weight"] for h in holdings], dtype=float)
    weights = raw_weights / raw_weights.sum()  # normalise to 1

    # ------------------------------------------------------------------
    # Portfolio returns (weighted sum of asset returns)
    # Ensure DatetimeIndex for resample() — the adapter receives date objects
    # from the test fixtures and from load_prices(); convert to Timestamps.
    # ------------------------------------------------------------------
    asset_returns = prices_df[symbols].copy()
    if not isinstance(asset_returns.index, pd.DatetimeIndex):
        asset_returns.index = pd.to_datetime(asset_returns.index)

    port_returns = (asset_returns * weights).sum(axis=1)

    # Align benchmark to portfolio index
    bench_idx = benchmark_returns.copy()
    if not isinstance(bench_idx.index, pd.DatetimeIndex):
        bench_idx.index = pd.to_datetime(bench_idx.index)
    bench = bench_idx.reindex(port_returns.index).fillna(0.0)

    # ------------------------------------------------------------------
    # Confidence level for metrics.* calls (= 1 - tail_alpha)
    # ------------------------------------------------------------------
    conf_level = 1.0 - tail_alpha  # e.g. 0.95

    # ------------------------------------------------------------------
    # Portfolio-level performance metrics
    # ------------------------------------------------------------------
    port_summary = _performance_metrics(port_returns, conf_level, pl_metrics)

    # ------------------------------------------------------------------
    # Benchmark performance metrics
    # ------------------------------------------------------------------
    bench_summary = _performance_metrics(bench, conf_level, pl_metrics)

    # ------------------------------------------------------------------
    # Per-asset metrics
    # ------------------------------------------------------------------
    per_asset = {}
    for sym in symbols:
        per_asset[sym] = _performance_metrics(asset_returns[sym], conf_level, pl_metrics)

    # ------------------------------------------------------------------
    # Annual returns
    # ------------------------------------------------------------------
    annual = _annual_returns(port_returns)

    # ------------------------------------------------------------------
    # Monthly return table  (for heatmap)
    # ------------------------------------------------------------------
    monthly = _monthly_return_table(port_returns, pl_metrics)

    # ------------------------------------------------------------------
    # VaR / ES  (alpha = tail probability, e.g. 0.05)
    # historical_var/expected_shortfall return a Series; take the last value
    # for the point-in-time estimate.
    # ------------------------------------------------------------------
    var95_series = pl_var.historical_var(port_returns, alpha=tail_alpha)
    var99_series = pl_var.historical_var(port_returns, alpha=0.01)
    es95_series  = pl_var.expected_shortfall(port_returns, alpha=tail_alpha)
    var95 = float(var95_series.iloc[-1])
    var99 = float(var99_series.iloc[-1])
    es95  = float(es95_series.iloc[-1])

    # ------------------------------------------------------------------
    # Tail diagnostics
    # jarque_bera returns a dict; hill_estimator returns a dict and needs k.
    # ------------------------------------------------------------------
    jb_result = pl_tail.jarque_bera(port_returns)
    jb_p = float(jb_result.get("p_value", jb_result.get("pvalue", 0.0)))
    # Hill estimator: use k = int(sqrt(n)) as a standard rule of thumb
    n = len(port_returns)
    k_hill = max(10, int(n ** 0.5))
    hill_result = pl_tail.hill_estimator(port_returns.abs(), k=k_hill)
    hill = float(hill_result.get("xi", hill_result.get("hill", 0.0)))
    skew = float(port_returns.skew())
    exkurt = float(port_returns.kurtosis())  # excess kurtosis

    # ------------------------------------------------------------------
    # Regime badge
    # ------------------------------------------------------------------
    regime_label = _detect_regime(port_returns, pl_regime)

    # ------------------------------------------------------------------
    # Correlation matrix
    # ------------------------------------------------------------------
    corr_labels, corr_matrix = _correlation(asset_returns, pl_cov)

    # ------------------------------------------------------------------
    # Efficient frontier + portfolio dot
    # ------------------------------------------------------------------
    frontier_data = _frontier(asset_returns, weights, pl_opt)

    # ------------------------------------------------------------------
    # Growth series (for chart)
    # ------------------------------------------------------------------
    growth_portfolio = _growth_series(port_returns)
    growth_benchmark = _growth_series(bench)

    # ------------------------------------------------------------------
    # Drawdown series
    # ------------------------------------------------------------------
    dd_series = _drawdown_series(port_returns, pl_metrics)

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------
    best_day = float(port_returns.max())
    worst_day = float(port_returns.min())
    pos_months_series = port_returns.resample("ME").apply(
        lambda r: (1 + r).prod() - 1
    )
    pos_months = float((pos_months_series > 0).mean())

    # ------------------------------------------------------------------
    # Data vintage
    # ------------------------------------------------------------------
    data_vintage = {
        "start": str(port_returns.index[0]),
        "end": str(port_returns.index[-1]),
    }

    return {
        "portfolio": port_summary,
        "benchmark": bench_summary,
        "annual": annual,
        "monthly": monthly,
        "per_asset": per_asset,
        "var95": var95,
        "var99": var99,
        "es95": es95,
        "skew": skew,
        "exkurt": exkurt,
        "jb_p": float(jb_p),
        "hill": hill,
        "best_day": best_day,
        "worst_day": worst_day,
        "pos_months": pos_months,
        "best": _best_year(annual),
        "worst": _worst_year(annual),
        "regime": regime_label,
        "correlation": {"labels": corr_labels, "matrix": corr_matrix},
        "frontier": frontier_data,
        "growth": {
            "dates": [str(d) for d in growth_portfolio.index.tolist()],
            "portfolio": growth_portfolio.tolist(),
            "benchmark": growth_benchmark.tolist(),
        },
        "drawdown": {
            "dates": [str(d) for d in dd_series.index.tolist()],
            "values": dd_series.tolist(),
        },
        "data_vintage": data_vintage,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _performance_metrics(returns: pd.Series, conf_level: float, pl_metrics) -> dict:
    """
    Compute CAGR, vol, Sharpe, Sortino, max DD, and end value ($10,000 start).
    portlab.metrics.sharpe/sortino use rf (risk-free rate) not alpha.
    We use rf=0.0 for simplicity (consistent with typical academic usage).
    """
    cagr_val = float(pl_metrics.cagr(returns))
    vol_val  = float(pl_metrics.ann_vol(returns))
    sh_val   = float(pl_metrics.sharpe(returns, rf=0.0))
    so_val   = float(pl_metrics.sortino(returns, rf=0.0))
    mdd_val  = float(pl_metrics.max_drawdown(returns))
    end_val  = float((1 + returns).prod() * 10_000)
    return {
        "cagr":    cagr_val,
        "vol":     vol_val,
        "sharpe":  sh_val,
        "sortino": so_val,
        "maxdd":   mdd_val,
        "end":     end_val,
    }


def _annual_returns(returns: pd.Series) -> dict[str, float]:
    annual = returns.resample("YE").apply(lambda r: float((1 + r).prod() - 1))
    return {str(d.year): v for d, v in annual.items()}


def _monthly_return_table(returns: pd.Series, pl_metrics) -> list[dict]:
    """
    Returns a list of {year, month, value} dicts for the heatmap chart.
    """
    monthly = returns.resample("ME").apply(lambda r: float((1 + r).prod() - 1))
    rows = []
    for d, v in monthly.items():
        rows.append({"year": d.year, "month": d.month, "value": v})
    return rows


def _detect_regime(returns: pd.Series, pl_regime) -> str:
    try:
        label = pl_regime.detect_regime(returns)
        if isinstance(label, pd.Series):
            label = label.iloc[-1]
        return str(label)
    except Exception:
        return "unknown"


def _correlation(asset_returns: pd.DataFrame, pl_cov) -> tuple[list[str], list[list[float]]]:
    labels = list(asset_returns.columns)
    try:
        cov = pl_cov.cov_sample(asset_returns)
        corr = pl_cov.corr_from_cov(cov)
    except Exception:
        corr = asset_returns.corr()
    matrix = [[round(float(corr.loc[r, c]), 4) for c in labels] for r in labels]
    return labels, matrix


def _frontier(
    asset_returns: pd.DataFrame,
    weights: np.ndarray,
    pl_opt,
    n_points: int = 30,
) -> dict:
    """
    Compute efficient frontier risk/return points + the portfolio dot.
    Returns {"points": [{"risk": ..., "return": ...}, ...], "portfolio": {"risk": ..., "return": ...}}.
    Falls back gracefully if the optimizer fails (e.g. too few assets).

    portlab.optimize.frontier(mu, cov, n_points, ...) signature:
      mu  = annualised expected returns (pd.Series)
      cov = annualised covariance matrix (pd.DataFrame)
    """
    try:
        import portlab.covariance as pl_cov2
        # Annualised mean returns and covariance
        mu = asset_returns.mean() * 252
        cov = pl_cov2.cov_sample(asset_returns) * 252
        frontier_result = pl_opt.frontier(mu, cov, n_points=n_points)
        # frontier() returns a DataFrame with columns: vol, ret (or similar)
        if hasattr(frontier_result, "columns"):
            cols = list(frontier_result.columns)
            vol_col  = next((c for c in cols if "vol" in c.lower() or "std" in c.lower()), cols[0])
            ret_col  = next((c for c in cols if "ret" in c.lower() or "mu" in c.lower()), cols[1])
            points = [
                {"risk": round(float(row[vol_col]), 6), "return": round(float(row[ret_col]), 6)}
                for _, row in frontier_result.iterrows()
            ]
        else:
            points = []
    except Exception as exc:
        logger.warning("frontier computation failed: %s", exc)
        points = []

    # Portfolio dot
    import portlab.metrics as pl_metrics
    port_returns_series = (asset_returns * weights).sum(axis=1)
    port_vol = float(pl_metrics.ann_vol(port_returns_series))
    port_ret = float(pl_metrics.cagr(port_returns_series))
    portfolio_dot = {"risk": round(port_vol, 6), "return": round(port_ret, 6)}

    return {"points": points, "portfolio": portfolio_dot}


def _growth_series(returns: pd.Series, initial: float = 10_000.0) -> pd.Series:
    return (1 + returns).cumprod() * initial


def _drawdown_series(returns: pd.Series, pl_metrics) -> pd.Series:
    try:
        dd = pl_metrics.drawdown_series(returns)
        return dd
    except Exception:
        # fallback: compute manually
        cum = (1 + returns).cumprod()
        rolling_max = cum.cummax()
        return (cum / rolling_max) - 1


def _best_year(annual: dict) -> list:
    if not annual:
        return []
    best = max(annual, key=annual.get)
    return [best, annual[best]]


def _worst_year(annual: dict) -> list:
    if not annual:
        return []
    worst = min(annual, key=annual.get)
    return [worst, annual[worst]]
