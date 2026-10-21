"""M4 gates on committed real-price fixtures; no network or synthetic market data."""

import json
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from django.test import Client

from apps.analysis.engine import run_tool_report
from apps.marketdata.models import PriceHistory, Security
from apps.tools.catalog import PORTFOLIO_TOOLS, TOOLS


PRICE_FILE = Path(__file__).parent / "fixtures/k5_prices.csv"
WEIGHTS = {"MCK": .2998, "LLY": .2355, "PWR": .1906, "NVDA": .1561, "STX": .118}
OPTIONS = {"window": 100, "years": 3, "simulations": 100, "steps": 5}


@pytest.fixture(scope="module")
def market():
    # Committed adjusted prices are the same source used by the M1 golden gate.
    prices = pd.read_csv(PRICE_FILE, index_col="date", parse_dates=True)
    returns = prices.pct_change().dropna()
    return prices, returns


@pytest.mark.parametrize("code", sorted(PORTFOLIO_TOOLS))
def test_every_tool_produces_finite_visual_and_table_from_real_prices(code, market):
    prices, returns = market
    report = run_tool_report(code, returns, prices, WEIGHTS, returns.SPY, OPTIONS)
    assert report["charts"], code
    assert report["rows"], code
    assert len(report["columns"]) == len(report["rows"][0]), code
    assert all(chart["option"].get("series") for chart in report["charts"]), code
    json.dumps(report, allow_nan=False)


def test_backtest_ending_balance_matches_portlab_on_fixture(market):
    import portlab.backtest as pl_backtest

    prices, returns = market
    expected = pl_backtest.backtest_portfolio(returns[list(WEIGHTS)], WEIGHTS,
                                             benchmark=returns.SPY, initial=10000)
    report = run_tool_report("backtest", returns, prices, WEIGHTS, returns.SPY, {})
    row = next(row for row in report["rows"] if row[0] == "Ending Balance")
    assert row[1] == pytest.approx(float(expected.balance.iloc[-1]), abs=1e-5)
    assert len(report["charts"]) == 3  # growth, drawdown, monthly heatmap
    assert report["charts"][2]["option"]["series"][0]["type"] == "heatmap"


def test_simulation_and_goal_share_seeded_engine_paths(market):
    import portlab.montecarlo as pl_mc

    prices, returns = market
    mc = run_tool_report("monte-carlo", returns, prices, WEIGHTS, returns.SPY, OPTIONS)
    goal = run_tool_report("goals", returns, prices, WEIGHTS, returns.SPY, OPTIONS)
    assert mc["rows"] == goal["rows"][:len(mc["rows"])]
    probability = next(row[1] for row in goal["rows"] if row[0] == "Success probability")
    assert 0 <= probability <= 1
    portfolio = returns[list(WEIGHTS)].mul(pd.Series(WEIGHTS)).sum(axis=1)
    monthly = portfolio.resample("ME").apply(lambda r: (1 + r).prod() - 1)
    if portfolio.index[0].day > 7:
        monthly = monthly.iloc[1:]
    if portfolio.index[-1] < portfolio.index[-1] + pd.offsets.BMonthEnd(0):
        monthly = monthly.iloc[:-1]
    direct = pl_mc.monte_carlo(initial=10000, years=3, n_sims=100,
                               model="bootstrap", hist_returns=monthly, seed=42)
    median = next(row[1] for row in mc["rows"] if row[0] == "p50")
    assert median == pytest.approx(float(direct.percentiles().p50.iloc[-1]), abs=.01)


def test_correlation_and_drawdown_match_direct_engine(market):
    import portlab.covariance as pl_cov
    import portlab.metrics as pl_metrics

    prices, returns = market
    corr = run_tool_report("correlations", returns, prices, WEIGHTS, returns.SPY, {})
    expected = pl_cov.corr_from_cov(pl_cov.cov_sample(returns[list(WEIGHTS)]))
    assert corr["rows"][0][1] == pytest.approx(expected.loc["MCK", "MCK"], abs=1e-3)
    dd = run_tool_report("drawdowns", returns, prices, WEIGHTS, returns.SPY, {})
    portfolio = returns[list(WEIGHTS)].mul(pd.Series(WEIGHTS)).sum(axis=1)
    series = dd["charts"][0]["option"]["series"][0]["data"]
    assert min(series) == pytest.approx(pl_metrics.drawdown_series(portfolio).min(), abs=1e-5)


@pytest.mark.django_db
def test_gallery_and_every_tool_route_returns_chart_with_cached_k5(client, market):
    prices, _ = market
    for symbol in prices:
        security = Security.objects.create(symbol=symbol)
        PriceHistory.objects.bulk_create([
            PriceHistory(security=security, date=day.date(),
                         close=Decimal(str(value)), adj_close=Decimal(str(value)))
            for day, value in prices[symbol].items()
        ], batch_size=1000)
    gallery = client.get("/tools/")
    assert gallery.status_code == 200
    assert len(gallery.context["cards"]) == 19
    for card in gallery.context["cards"]:
        assert client.get(card["url"]).status_code == 200, card["code"]
    payload = {
        "holdings_json": json.dumps([{"symbol": symbol, "weight": weight * 100}
                                      for symbol, weight in WEIGHTS.items()]),
        "benchmark": "SPY", "start_date": "2021-01-04",
        "end_date": str(prices.index[-1].date()),
        "years": 3, "simulations": 100, "window": 100, "steps": 5,
    }
    for code in sorted(PORTFOLIO_TOOLS):
        response = client.post(f"/tools/{code}", payload)
        assert response.status_code == 200, code
        assert response.context["report"], (code, response.context["portfolio_form"].errors)
        assert b'tool-chart-data' in response.content, code


@pytest.mark.django_db
@pytest.mark.parametrize("parameter,value", [("years", "1000"),
                                               ("simulations", "10001"),
                                               ("initial", "NaN")])
def test_simulation_rejects_unbounded_inputs(client, parameter, value):
    response = client.post("/tools/monte-carlo", {parameter: value})
    assert response.status_code == 200
    assert "report" not in response.context
    assert b"allowed range" in response.content or b"finite nonnegative" in response.content
