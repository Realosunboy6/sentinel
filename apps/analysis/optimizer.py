"""Load a selected portfolio from cached prices; never request market data."""
from calendar import monthrange
from datetime import date

from .analyzer import prepare_prices, make_returns
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
    try:
        holdings, prices, warnings = prepare_prices(holdings, start, end)
    except ValueError as exc:
        raise OptimizationInputError(str(exc)) from exc
    returns = make_returns(prices)
    returns.attrs['warnings'] = warnings
    current = {h['symbol']: h['weight'] for h in holdings}
    return returns, current


def optimize_portfolio(returns, current, **options):
    report = run_optimization(returns, current, **options)
    report["warnings"] = returns.attrs.get("warnings", [])
    return report, optimization_charts(report)


def rolling_portfolio(returns, current, **options):
    report = run_rolling_optimization(returns, current, **options)
    report["warnings"] = returns.attrs.get("warnings", [])
    charts = {} if report["young_history"] else {"rolling": rolling_weights_chart(report)}
    return report, charts
