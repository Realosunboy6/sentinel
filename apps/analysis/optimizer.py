"""Load a selected portfolio from cached prices; never request market data."""
from calendar import monthrange
from datetime import date

from .analyzer import load_prices, make_returns
from .engine import OptimizationInputError, run_optimization, run_rolling_optimization
from .models import Analysis
from .charts import optimization_charts, rolling_weights_chart


def load_optimization_portfolio(slug):
    analysis = Analysis.objects.get(slug=slug)
    holdings = analysis.inputs.get("holdings", [])
    symbols = [h["symbol"] for h in holdings]
    if not symbols:
        raise OptimizationInputError("This analysis has no portfolio holdings.")
    today = date.today()
    year = today.year - 10
    default_start = today.replace(year=year, day=min(today.day, monthrange(year, today.month)[1]))
    start = date.fromisoformat(analysis.inputs.get("start", str(default_start)))
    end = date.fromisoformat(analysis.inputs.get("end", str(today)))
    returns, current = load_optimization_inputs(holdings, start, end)
    return analysis, returns, current


def load_optimization_inputs(holdings, start, end):
    """Load temporary tool inputs without saving or mutating an analysis."""
    symbols = [h["symbol"] for h in holdings]
    prices = load_prices(symbols, start, end)
    missing = set(symbols) - set(prices.columns)
    if prices.empty or missing:
        raise OptimizationInputError("Cached price history is unavailable for: " + ", ".join(sorted(missing or set(symbols))))
    returns = make_returns(prices[symbols])
    current = {h["symbol"]: h["weight"] for h in holdings}
    return returns, current


def optimize_portfolio(returns, current, **options):
    report = run_optimization(returns, current, **options)
    return report, optimization_charts(report)


def rolling_portfolio(returns, current, **options):
    report = run_rolling_optimization(returns, current, **options)
    charts = {} if report["young_history"] else {"rolling": rolling_weights_chart(report)}
    return report, charts
