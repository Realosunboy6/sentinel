"""
RiskLens orchestrator.

Entry point: get_risklens(analysis_slug) -> (Analysis, dict, dict)

Loads portfolio returns from price_history for the holdings stored in an
Analysis row, calls engine.run_risklens(), and builds chart payloads.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from apps.analysis.analyzer import load_prices, make_returns
from apps.analysis.charts import histogram_chart, regime_panel_chart
from apps.analysis.engine import EngineUnavailableError, run_risklens
from apps.analysis.models import Analysis, AnalysisResult

logger = logging.getLogger(__name__)

DEFAULT_YEARS = 10


def get_risklens(slug: str) -> tuple[Analysis, dict, dict]:
    """
    Load an Analysis, derive portfolio returns, run run_risklens(), build charts.

    Returns
    -------
    (Analysis, risk_metrics dict, charts dict)
    """
    analysis = Analysis.objects.get(slug=slug)
    stored_holdings = analysis.inputs.get("holdings", [])
    benchmark_symbol = analysis.inputs.get("settings", {}).get("benchmark", "SPY")

    symbols = [h["symbol"] for h in stored_holdings]
    all_symbols = symbols + ([benchmark_symbol] if benchmark_symbol not in symbols else [])

    # Date window: use stored start date or default 10y
    stored_start = analysis.inputs.get("start")
    if stored_start:
        start_date = date.fromisoformat(stored_start)
    else:
        today = date.today()
        start_date = date(today.year - DEFAULT_YEARS, today.month, today.day)

    prices_df = load_prices(all_symbols, start_date, date.today())
    if prices_df.empty:
        raise EngineUnavailableError("No price data available for this analysis.")

    returns_df = make_returns(prices_df)
    weights = [h["weight"] for h in stored_holdings]
    weight_sum = sum(weights)
    norm_weights = [w / weight_sum for w in weights]

    port_returns = (returns_df[symbols] * norm_weights).sum(axis=1)

    asof = str(prices_df.index.max().date()
               if hasattr(prices_df.index.max(), "date")
               else prices_df.index.max())

    risk_metrics = run_risklens(port_returns)
    charts = _build_risk_charts(risk_metrics, asof)

    return analysis, risk_metrics, charts


def _build_risk_charts(risk_metrics: dict, asof: str) -> dict:
    h = risk_metrics["histogram"]
    r = risk_metrics["regime"]
    return {
        "histogram": histogram_chart(
            bins=h["bins"],
            counts=h["counts"],
            var95_line=h["var95_line"],
            var99_line=h["var99_line"],
            asof=asof,
        ),
        "regime": regime_panel_chart(
            calm_var95=r["calm_var95"],
            stressed_var95=r["stressed_var95"],
            full_var95=r["full_var95"],
            asof=asof,
        ),
    }
