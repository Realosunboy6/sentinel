"""
portlab engine adapter — the ONLY module in this repo that imports portlab.

All analysis calls go through run_analysis() or run_risklens(). The rest of the app never
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


class OptimizationInputError(ValueError):
    """An input or insufficient history prevents a requested optimization."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def engine_version():
    """Resolve engine metadata within the adapter, keeping imports lazy."""
    from importlib.metadata import version, PackageNotFoundError
    try:
        return version('portlab')
    except PackageNotFoundError as exc:
        raise EngineUnavailableError('portlab is not installed.') from exc


def _json_finite(value):
    if isinstance(value, dict):
        return {k: _json_finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_finite(v) for v in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    return value


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
        return _json_finite(_run(
            holdings, prices_df, benchmark_returns, tail_alpha,
            pl_metrics, pl_var, pl_tail, pl_regime, pl_cov, pl_opt,
        ))
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
    n = len(port_returns)
    jb_result = pl_tail.jarque_bera(port_returns) if n >= 8 else {}
    jb_p = jb_result.get('p_value', jb_result.get('pvalue'))
    losses = -port_returns
    k_hill = min(max(2, int(n ** .5)), int((losses > 0).sum()), n - 1)
    hill = float(pl_tail.hill_estimator(losses, k=k_hill)['xi']) if k_hill >= 2 else None
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
        "jb_p": jb_p,
        "hill": hill,
        "best_day": best_day,
        "worst_day": worst_day,
        "pos_months": pos_months,
        "best": _best_year(annual),
        "worst": _worst_year(annual),
        "regime": regime_label,
        "young_history": len(port_returns) < 60,
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
    vol_val  = float(pl_metrics.ann_vol(returns)) if len(returns) >= 2 else None
    sh_val   = float(pl_metrics.sharpe(returns, rf=0.0)) if len(returns) >= 2 else None
    so_val   = float(pl_metrics.sortino(returns, rf=0.0)) if len(returns) >= 2 else None
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
        return {0: "Calm", 1: "Stressed"}.get(label, "Unknown")
    except Exception:
        return "unknown"


def _correlation(asset_returns: pd.DataFrame, pl_cov) -> tuple[list[str], list[list[float]]]:
    labels = list(asset_returns.columns)
    if len(asset_returns) < 2:
        return labels, [[None for _ in labels] for _ in labels]
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
    if len(asset_returns) < 2:
        return {'points': [], 'portfolio': {'risk': None, 'return': None}}
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
    port_ret = float(weights @ (asset_returns.mean() * 252))
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


# ---------------------------------------------------------------------------
# RiskLens entry point
# ---------------------------------------------------------------------------

# Product threshold for displaying backtests, after the rolling warmup.
# This is a UI policy, not a guarantee of asymptotic test accuracy.
_MIN_BACKTEST_SCORED = 250


def run_risklens(
    port_returns: pd.Series,
    tail_alpha: float = 0.05,
    backtest_window: int = 250,
) -> dict:
    """
    Compute the full RiskLens report for a portfolio return series.

    Parameters
    ----------
    port_returns:
        Daily simple returns Series with a DatetimeIndex (or date index,
        converted internally).
    tail_alpha:
        Tail probability (default 0.05 → 95% confidence).
    backtest_window:
        Rolling window for the historical VaR backtest (default 250).

    Returns
    -------
    dict with keys: var_table, backtest, regime, tail, histogram, data_vintage.
    All VaR values are positive = loss (spec §5.2).
    """
    try:
        import portlab.risk.var as pl_var
        import portlab.risk.backtest as pl_bt
        import portlab.risk.tail as pl_tail
        import portlab.risk.regime as pl_regime
    except ImportError as exc:
        raise EngineUnavailableError(
            f"portlab is not importable: {exc}.  "
            "Install it with: pip install portlab[opt]==0.2.2"
        ) from exc

    try:
        return _run_risklens(
            port_returns, tail_alpha, backtest_window,
            pl_var, pl_bt, pl_tail, pl_regime,
        )
    except EngineUnavailableError:
        raise
    except Exception as exc:
        logger.exception("engine.run_risklens failed")
        raise EngineUnavailableError(f"RiskLens engine error: {exc}") from exc


def _run_risklens(port_returns, tail_alpha, backtest_window, pl_var, pl_bt, pl_tail, pl_regime):
    # Ensure DatetimeIndex
    returns = port_returns.copy()
    if not isinstance(returns.index, pd.DatetimeIndex):
        returns.index = pd.to_datetime(returns.index)

    n = len(returns)
    if n < 1 or not np.isfinite(returns.to_numpy(dtype=float)).all():
        raise ValueError("RiskLens needs finite daily returns.")
    if n == 1:
        histogram = _build_histogram(returns, 0.0, 0.0)
        histogram['var95_line'] = histogram['var99_line'] = None
        backtest = {key: None for key in ['kupiec_lr', 'kupiec_p', 'kupiec_reject', 'chris_n00', 'chris_n01', 'chris_n10', 'chris_n11', 'chris_lr', 'chris_p', 'joint_lr', 'joint_p']}
        backtest.update(n_scored=0, n_exceptions=0, young_history=True, basel_zone='INSUFFICIENT DATA')
        return {'var_table': [{'method': method, 'var95': None, 'var99': None, 'es95': None, 'es99': None} for method in ['Historical', 'Parametric', 'Parametric (t)', 'Cornish-Fisher', 'GARCH']],
            'backtest': backtest, 'regime': {'current': 'Unknown', 'calm_var95': None, 'stressed_var95': None, 'full_var95': None},
            'tail': {'skew': None, 'exkurt': None, 'jb_p': None, 'hill': None, 'worst_day': float(returns.min()), 'best_day': float(returns.max())},
            'histogram': histogram, 'stress_scenarios': [], 'data_vintage': {'start': str(returns.index[0].date()), 'end': str(returns.index[-1].date())},
            'var95': None, 'var99': None, 'es95': None, 'es99': None, 'basel_zone': 'INSUFFICIENT DATA',
            'drawdown': {'dates': [str(returns.index[0].date())], 'values': [0.0]}}

    alpha99 = 0.01  # tail probability for 99% VaR
    # A single final expanding forecast: same observations and alignment as
    # window=None, without fitting Student-t MLE on every intermediate day.
    point_window = n - 1 if n > 2 else None

    # ------------------------------------------------------------------
    # Full-sample point-in-time VaR / ES (last value of rolling series)
    # ------------------------------------------------------------------
    hist_var95  = float(pl_var.historical_var(returns, alpha=tail_alpha, window=point_window).iloc[-1])
    hist_var99  = float(pl_var.historical_var(returns, alpha=alpha99, window=point_window).iloc[-1])
    hist_es95   = float(pl_var.expected_shortfall(returns, alpha=tail_alpha, window=point_window).iloc[-1])
    hist_es99 = float(pl_var.expected_shortfall(returns, alpha=alpha99, window=point_window).iloc[-1])

    # Parametric (mean="constant" per spec §5.4)
    param_var95 = _finite_or_none(pl_var.parametric_var(returns, alpha=tail_alpha, mean="constant", window=point_window).iloc[-1])
    param_var99 = _finite_or_none(pl_var.parametric_var(returns, alpha=alpha99, mean="constant", window=point_window).iloc[-1])

    # Student-t parametric
    parm_t_var95 = _finite_or_none(pl_var.parametric_var_t(returns, alpha=tail_alpha, window=point_window).iloc[-1])
    parm_t_var99 = _finite_or_none(pl_var.parametric_var_t(returns, alpha=alpha99, window=point_window).iloc[-1])

    # Cornish-Fisher
    cf_var95 = _finite_or_none(pl_var.cornish_fisher_var(returns, alpha=tail_alpha, window=point_window).iloc[-1])
    cf_var99 = _finite_or_none(pl_var.cornish_fisher_var(returns, alpha=alpha99, window=point_window).iloc[-1])

    # GARCH (mean="zero" per spec §5.4)
    try:
        # Only the latest forecast is displayed. Its trailing window is identical
        # to the last forecast of a full rolling run, avoiding thousands of fits.
        recent = returns.iloc[-(backtest_window + 1):]
        garch_var95 = _finite_or_none(pl_var.garch_var(recent, alpha=tail_alpha, window=backtest_window, mean="zero").iloc[-1])
        garch_var99 = _finite_or_none(pl_var.garch_var(recent, alpha=alpha99, window=backtest_window, mean="zero").iloc[-1])
    except Exception as exc:
        logger.warning("garch_var unavailable: %s", exc)
        garch_var95 = garch_var99 = None

    var_table = [
        {"method": "Historical",       "var95": hist_var95,   "var99": hist_var99,   "es95": hist_es95, "es99": hist_es99},
        {"method": "Parametric",       "var95": param_var95,  "var99": param_var99,  "es95": None, "es99": None},
        {"method": "Parametric (t)",   "var95": parm_t_var95, "var99": parm_t_var99, "es95": None, "es99": None},
        {"method": "Cornish-Fisher",   "var95": cf_var95,     "var99": cf_var99,     "es95": None, "es99": None},
        {"method": "GARCH",            "var95": garch_var95,  "var99": garch_var99,  "es95": None, "es99": None},
    ]

    # ------------------------------------------------------------------
    # Rolling-window VaR backtest (spec §5.3: nullable-boolean handling)
    # ------------------------------------------------------------------
    var_series = pl_var.historical_var(returns, alpha=tail_alpha, window=backtest_window)
    exc = pl_bt.exceptions(returns, var_series)   # nullable-boolean Series — DO NOT dropna

    scored = exc.dropna()   # only for counting — not passed to backtest functions
    n_scored    = len(scored)
    n_exceptions = int(scored.sum())
    young_history = n_scored < _MIN_BACKTEST_SCORED

    if young_history:
        backtest = {
            "n_scored": n_scored,
            "n_exceptions": n_exceptions,
            "young_history": True,
            "kupiec_lr": None, "kupiec_p": None, "kupiec_reject": None,
            "chris_n00": None, "chris_n01": None, "chris_n10": None, "chris_n11": None,
            "chris_lr": None, "chris_p": None,
            "joint_lr": None, "joint_p": None,
            "basel_zone": "INSUFFICIENT DATA",
        }
    else:
        kup   = pl_bt.kupiec_pof(exc, alpha=tail_alpha)
        chris = pl_bt.christoffersen_ind(exc)
        joint = pl_bt.joint_test(exc, alpha=tail_alpha)
        # Basel uses 99% forecasts over the latest 250 scored observations,
        # separately from the 95% full-history likelihood-ratio tests.
        var99_series = pl_var.historical_var(returns, alpha=0.01, window=backtest_window)
        basel_scored = pl_bt.exceptions(returns, var99_series).dropna().iloc[-250:]
        bt_result = pl_bt.basel_traffic_light(int(basel_scored.sum()), n_obs=len(basel_scored), alpha=0.01)
        backtest = {
            "n_scored":       n_scored,
            "n_exceptions":   n_exceptions,
            "young_history":  False,
            "kupiec_lr":      float(kup["lr_stat"]),
            "kupiec_p":       float(kup["p_value"]),
            "kupiec_reject":  bool(kup["reject"]),
            "chris_n00":      int(chris["n00"]),
            "chris_n01":      int(chris["n01"]),
            "chris_n10":      int(chris["n10"]),
            "chris_n11":      int(chris["n11"]),
            "chris_lr":       float(chris["lr_stat"]),
            "chris_p":        float(chris["p_value"]),
            "joint_lr":       float(joint["lr_stat"]),
            "joint_p":        float(joint["p_value"]),
            "basel_zone":     str(bt_result.get("zone", "UNKNOWN")),
            "basel_n_scored": len(basel_scored),
            "basel_n_exceptions": int(basel_scored.sum()),
        }

    # ------------------------------------------------------------------
    # Regime-conditional VaR
    # ------------------------------------------------------------------
    try:
        regime_series = pl_regime.detect_regime(returns)
        rv = pl_regime.regime_var(returns, alpha=tail_alpha, regime=regime_series)
        calm_var95 = _finite_or_none(rv["calm_var"])
        stressed_var95 = _finite_or_none(rv["stressed_var"])
        full_var95 = _finite_or_none(rv["full_var"])
        current_regime = {0: "Calm", 1: "Stressed"}.get(rv["current_regime"], "Unknown")
    except Exception as exc:
        logger.warning("regime_var unavailable: %s", exc)
        calm_var95 = stressed_var95 = None
        full_var95 = hist_var95
        current_regime = "unknown"

    regime = {
        "current":      current_regime,
        "calm_var95":   calm_var95,
        "stressed_var95": stressed_var95,
        "full_var95":   full_var95,
    }

    # ------------------------------------------------------------------
    # Tail diagnostics
    # ------------------------------------------------------------------
    jb_result = pl_tail.jarque_bera(returns) if n >= 8 else {}
    jb_p = jb_result.get("p_value", jb_result.get("pvalue"))
    losses = -returns
    k_hill = min(max(2, int(n ** 0.5)), int((losses > 0).sum()), n - 1)
    hill = float(pl_tail.hill_estimator(losses, k=k_hill)["xi"]) if k_hill >= 2 else None

    tail = {
        "skew":     _finite_or_none(returns.skew()),
        "exkurt":   _finite_or_none(returns.kurtosis()),
        "jb_p":     _finite_or_none(jb_p),
        "hill":     hill,
        "worst_day": float(returns.min()),
        "best_day":  float(returns.max()),
    }

    # ------------------------------------------------------------------
    # Histogram data (pre-binned for ECharts)
    # ------------------------------------------------------------------
    histogram = _build_histogram(returns, hist_var95, hist_var99)
    stress_scenarios = _historical_stress(returns)

    # ------------------------------------------------------------------
    # Data vintage
    # ------------------------------------------------------------------
    data_vintage = {
        "start": str(returns.index[0].date() if hasattr(returns.index[0], "date") else returns.index[0]),
        "end":   str(returns.index[-1].date() if hasattr(returns.index[-1], "date") else returns.index[-1]),
    }

    return {
        "var_table":    var_table,
        "backtest":     backtest,
        "regime":       regime,
        "tail":         tail,
        "histogram":    histogram,
        "stress_scenarios": stress_scenarios,
        "data_vintage": data_vintage,
        # Convenience copies for the KPI bar
        "var95":  hist_var95,
        "var99":  hist_var99,
        "es95":   hist_es95,
        "es99":   hist_es99,
        "basel_zone": backtest["basel_zone"],
        "drawdown": {"dates": [str(d.date()) for d in returns.index],
                     "values": _drawdown_series(returns, None).tolist()},
    }


def _finite_or_none(value):
    return float(value) if value is not None and np.isfinite(value) else None


def _historical_stress(returns):
    """Replay observed constant-mix portfolio paths, never invented shocks."""
    from portlab.stress import scenario_shocks

    wealth = (1 + returns).cumprod().to_frame("portfolio")
    rows = []
    for label, start, end in (
        ("COVID crash", "2020-02-19", "2020-03-23"),
        ("2022 bear market", "2022-01-03", "2022-10-12"),
    ):
        available = returns.index.min() <= pd.Timestamp(start) and returns.index.max() >= pd.Timestamp(end)
        value = float(scenario_shocks(wealth, start, end)["portfolio"]) if available else None
        rows.append({"name": label, "start": start, "end": end, "return": value,
                     "note": "Observed daily constant-mix replay" if available else "Cached analysis history does not cover this episode"})
    return rows


def _build_histogram(returns: pd.Series, var95: float, var99: float, n_bins: int = 40) -> dict:
    """Pre-bin daily returns for the histogram chart."""
    import numpy as np
    counts, bin_edges = np.histogram(returns.dropna(), bins=n_bins)
    bin_centers = [(bin_edges[i] + bin_edges[i + 1]) / 2 for i in range(n_bins)]
    return {
        "bins":      [round(float(c), 6) for c in bin_centers],
        "counts":    [int(c) for c in counts],
        "var95_line": round(float(-var95), 6),   # negative = left tail
        "var99_line": round(float(-var99), 6),
    }


# ---------------------------------------------------------------------------
# M3: optimization. All portlab imports stay inside this adapter.
# ---------------------------------------------------------------------------

def run_optimization(asset_returns, current_weights, method="max_sharpe",
                     max_weight=0.5, rf=0.0, views=None, tc_bps=10.0):
    """Bounded portfolio optimization on cached daily simple returns."""
    from apps.analysis.optimization_options import METHODS

    returns, current = _optimization_inputs(asset_returns, current_weights, max_weight)
    if method not in METHODS:
        raise OptimizationInputError("Choose a supported optimization method.")
    if not np.isfinite(rf) or not np.isfinite(tc_bps) or tc_bps < 0:
        raise OptimizationInputError("Risk-free rate and trading cost must be finite; cost cannot be negative.")
    try:
        import portlab.optimize as opt
        import portlab.metrics as metrics
        mu, cov = opt.mean_cov(returns, cov_method="ledoit_wolf")
        estimate_mu = mu
        if method == "black_litterman":
            estimate_mu = _bl_returns(opt, cov, current, views, rf)
        weights = _solve_optimization(opt, returns, estimate_mu, cov, current,
                                      method, max_weight, rf, tc_bps)
        _check_solution(weights, max_weight)
        frontier = _bounded_frontier(opt, estimate_mu, cov, current, max_weight, rf)
        current_stats = opt.portfolio_stats(current.values, estimate_mu, cov, rf)
        optimized_stats = opt.portfolio_stats(weights.values, estimate_mu, cov, rf)
        for stats, allocation in ((current_stats, current), (optimized_stats, weights)):
            stats["cvar95"] = float(metrics.cvar_historical(returns @ allocation, alpha=.95))
        traded_notional = float((weights - current).abs().sum())
        current_risk = opt.risk_contributions(current, cov)
        optimized_risk = opt.risk_contributions(weights, cov)
        report = {
            "method": method, "method_label": METHODS[method],
            "weights": [{"symbol": s, "current": float(current[s]),
                         "optimized": float(weights[s]), "change": float(weights[s] - current[s]),
                         "current_risk": float(current_risk[s]),
                         "optimized_risk": float(optimized_risk[s])} for s in returns.columns],
            "current": current_stats, "optimized": optimized_stats,
            "frontier": frontier,
            "turnover": traded_notional / 2, "traded_notional": traded_notional,
            "estimated_cost": traded_notional * tc_bps / 10000,
            "max_weight": float(max_weight), "rf": float(rf), "tc_bps": float(tc_bps),
            "n_observations": len(returns),
            "return_basis": "Black-Litterman posterior (entered weights as reference prior)" if method == "black_litterman" else "Historical annualized arithmetic mean",
            "data_vintage": {"start": str(returns.index[0].date()), "end": str(returns.index[-1].date())},
        }
        # Refuse nonfinite payloads before the template or JSON serializer sees them.
        import json
        json.dumps(report, allow_nan=False)
        return report
    except (OptimizationInputError, EngineUnavailableError):
        raise
    except Exception as exc:
        logger.exception("engine.run_optimization failed")
        raise EngineUnavailableError("The optimizer could not compute a valid allocation.") from exc


def _optimization_inputs(asset_returns, current_weights, max_weight):
    from apps.analysis.optimization_options import MIN_OBSERVATIONS

    returns = pd.DataFrame(asset_returns, dtype=float).copy()
    if returns.empty or len(returns) < MIN_OBSERVATIONS:
        raise OptimizationInputError(f"Optimization needs {MIN_OBSERVATIONS}+ daily return observations.")
    if not 1 <= len(returns.columns) <= 25 or returns.columns.has_duplicates:
        raise OptimizationInputError("Choose 1 to 25 distinct portfolio holdings.")
    if not np.isfinite(returns.to_numpy()).all() or (returns <= -1).any().any():
        raise OptimizationInputError("Cached returns must be finite and greater than -100%.")
    returns.index = pd.to_datetime(returns.index)
    if not returns.index.is_monotonic_increasing or returns.index.has_duplicates:
        raise OptimizationInputError("Return observations must have distinct, increasing dates.")
    if not np.isfinite(max_weight) or not 0 < max_weight <= 1 or max_weight * len(returns.columns) < 1 - 1e-10:
        raise OptimizationInputError("The weight cap is infeasible: holdings count times cap must be at least 100%.")
    current = pd.Series(current_weights, dtype=float).reindex(returns.columns)
    if not np.isfinite(current.to_numpy()).all() or (current < 0).any() or current.sum() <= 0:
        raise OptimizationInputError("Current weights must be finite, nonnegative, and have a positive sum.")
    current /= current.sum()
    if (returns.std() <= 1e-12).any():
        raise OptimizationInputError("Optimization needs nonconstant return history for every holding.")
    return returns, current


def _bl_returns(opt, cov, current, views, rf):
    if not views:
        raise OptimizationInputError("Black-Litterman needs at least one explicit return view.")
    picks, targets, confidence = [], [], []
    seen = set()
    for view in views:
        symbol = view.get("symbol")
        target = float(view.get("return", float("nan")))
        conf = float(view.get("confidence", float("nan")))
        if symbol not in cov.columns or symbol in seen or not np.isfinite(target) or target <= -1 or not np.isfinite(conf) or not 0 < conf <= 1:
            raise OptimizationInputError("Views need distinct portfolio symbols, finite returns above -100%, and confidence in (0, 100%].")
        seen.add(symbol)
        picks.append([float(s == symbol) for s in cov.columns])
        targets.append(target)
        confidence.append(conf)
    return opt.black_litterman(cov, current, pd.DataFrame(picks, columns=cov.columns),
        pd.Series(targets), view_confidence=pd.Series(confidence), rf=rf)


def _solve_optimization(opt, returns, mu, cov, current, method, cap, rf, tc_bps):
    bounds = (0.0, cap)
    if method in ("max_sharpe", "black_litterman"):
        result = opt.max_sharpe(mu, cov, rf=rf, bounds=bounds, solver="slsqp")
    elif method == "gmv":
        result = opt.gmv(mu, cov, bounds=bounds, solver="slsqp")
    elif method == "risk_parity":
        result = opt.equal_risk_contribution(cov, bounds=bounds)
    elif method == "min_cvar":
        result = opt.min_cvar(returns, alpha=.95, bounds=bounds)
    else:
        result = opt.opt_constrained(mu, cov, w_prev=current, tc_bps=tc_bps,
                                     risk_aversion=5.0, bounds=bounds, rf=rf)
    return result.reindex(returns.columns)


def _check_solution(weights, cap):
    values = weights.to_numpy(dtype=float)
    if not np.isfinite(values).all() or abs(values.sum() - 1) > 1e-6 or values.min() < -1e-6 or values.max() > cap + 1e-6:
        raise EngineUnavailableError("The optimizer returned an allocation outside the requested constraints.")


def _bounded_frontier(opt, mu, cov, current, cap, rf, n_points=25):
    """Use public portlab solves on targets feasible under the same asset cap."""
    gmv = opt.gmv(mu, cov, bounds=(0.0, cap), solver="slsqp")
    _check_solution(gmv, cap)
    # Linear maximum-return endpoint under uniform box constraints.
    high = pd.Series(0.0, index=mu.index)
    remaining = 1.0
    for symbol in mu.sort_values(ascending=False).index:
        high[symbol] = min(cap, remaining)
        remaining -= high[symbol]
        if remaining <= 1e-12:
            break
    low_return = float(gmv @ mu)
    high_return = float(high @ mu)
    points = []
    for target in np.linspace(low_return, high_return, n_points):
        weights = opt.min_vol_at_return(mu, cov, float(target), bounds=(0.0, cap), solver="slsqp")
        _check_solution(weights, cap)
        stats = opt.portfolio_stats(weights.values, mu, cov, rf)
        if abs(stats["return"] - target) > 1e-5:
            raise EngineUnavailableError("A frontier solve did not reach its requested return.")
        points.append({"risk": stats["volatility"], "return": stats["return"]})
    return {"points": points,
        "portfolio": _portfolio_point(opt, current, mu, cov, rf)}


def _portfolio_point(opt, weights, mu, cov, rf):
    stats = opt.portfolio_stats(weights.values, mu, cov, rf)
    return {"risk": stats["volatility"], "return": stats["return"]}


def run_rolling_optimization(asset_returns, current_weights, method="gmv",
                             max_weight=.5, lookback=252, step=21, rf=0.0, tc_bps=10.0):
    """Dated target allocations; each estimation window ends before its decision date."""
    from apps.analysis.optimization_options import ROLLING_METHODS, MIN_OBSERVATIONS
    returns, current = _optimization_inputs(asset_returns, current_weights, max_weight)
    if method not in ROLLING_METHODS:
        raise OptimizationInputError("Choose a supported rolling method.")
    if not isinstance(lookback, int) or not MIN_OBSERVATIONS <= lookback <= 1260 or not isinstance(step, int) or not 5 <= step <= 252:
        raise OptimizationInputError("Lookback must be 60 to 1260 days; rebalance interval 5 to 252 days.")
    if not np.isfinite(tc_bps) or tc_bps < 0 or not np.isfinite(rf):
        raise OptimizationInputError("Trading cost and risk-free rate must be finite; cost cannot be negative.")
    if len(returns) <= lookback:
        return {"young_history": True, "message": f"Rolling optimization needs {lookback + 1}+ daily return observations.", "rows": [],
                "symbols": list(returns.columns), "method_label": ROLLING_METHODS[method]}
    try:
        import portlab.optimize as opt
        rows = []
        previous = current.copy()
        last_position = None
        for position in range(lookback, len(returns), step):
            sample = returns.iloc[position - lookback:position]
            if last_position is not None:
                previous *= (1 + returns.iloc[last_position:position]).prod()
                previous /= previous.sum()
            mu, cov = opt.mean_cov(sample, cov_method="ledoit_wolf")
            weights = _solve_optimization(opt, sample, mu, cov, previous, method, max_weight, rf, tc_bps)
            _check_solution(weights, max_weight)
            traded = float((weights - previous).abs().sum())
            rows.append({"date": str(returns.index[position].date()),
                         "training_end": str(sample.index[-1].date()),
                         "weights": {s: float(weights[s]) for s in returns.columns},
                         "turnover": traded / 2, "estimated_cost": traded * tc_bps / 10000})
            previous = weights.copy()
            last_position = position
        return {"young_history": False, "rows": rows, "symbols": list(returns.columns),
                "lookback": lookback, "step": step, "method_label": ROLLING_METHODS[method],
                "data_vintage": {"start": str(returns.index[0].date()), "end": str(returns.index[-1].date())}}
    except (OptimizationInputError, EngineUnavailableError):
        raise
    except Exception as exc:
        logger.exception("engine.run_rolling_optimization failed")
        raise EngineUnavailableError("Rolling optimization could not compute valid allocations.") from exc
