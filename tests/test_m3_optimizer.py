"""M3 regressions on the committed real K5 fixture; tolerances stated below."""
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from apps.analysis.engine import (EngineUnavailableError, OptimizationInputError,
    run_optimization, run_rolling_optimization)

FIXTURE = Path(__file__).parent / "fixtures" / "k5_prices.csv"
SYMBOLS = ["MCK", "LLY", "PWR", "NVDA", "STX"]
CURRENT = dict(zip(SYMBOLS, [.2998, .2355, .1906, .1561, .1180]))
VIEWS = [{"symbol": "MCK", "return": .12, "confidence": .6}]


@pytest.fixture(scope="module")
def returns():
    return pd.read_csv(FIXTURE, index_col="date", parse_dates=True)[SYMBOLS].pct_change().dropna()


@pytest.fixture(scope="module")
def optimized(returns):
    return run_optimization(returns, CURRENT)


def weights_of(report):
    return pd.Series({row["symbol"]: row["optimized"] for row in report["weights"]}).reindex(SYMBOLS)


def test_max_sharpe_direct_gate(returns, optimized):
    import portlab.optimize as opt
    mu, cov = opt.mean_cov(returns, cov_method="ledoit_wolf")
    direct = opt.max_sharpe(mu, cov, rf=0, bounds=(0, .5), solver="slsqp")
    # Locked M3 gate: absolute weight error <= 1e-4 vs same pinned public API.
    np.testing.assert_allclose(weights_of(optimized), direct.reindex(SYMBOLS), atol=1e-4, rtol=0)
    json.dumps(optimized, allow_nan=False)


@pytest.mark.parametrize("method", ["gmv", "risk_parity", "min_cvar", "black_litterman", "turnover_aware"])
def test_methods_match_direct_portlab(returns, method):
    import portlab.optimize as opt
    mu, cov = opt.mean_cov(returns, cov_method="ledoit_wolf")
    current = pd.Series(CURRENT).reindex(SYMBOLS)
    result = run_optimization(returns, CURRENT, method=method, views=VIEWS)
    if method == "gmv":
        expected = opt.gmv(mu, cov, bounds=(0, .5), solver="slsqp")
    elif method == "risk_parity":
        expected = opt.equal_risk_contribution(cov, bounds=(0, .5))
    elif method == "min_cvar":
        expected = opt.min_cvar(returns, alpha=.95, bounds=(0, .5))
    elif method == "black_litterman":
        posterior = opt.black_litterman(cov, current,
            pd.DataFrame([[1, 0, 0, 0, 0]], columns=SYMBOLS), pd.Series([.12]),
            view_confidence=pd.Series([.6]), rf=0)
        expected = opt.max_sharpe(posterior, cov, rf=0, bounds=(0, .5), solver="slsqp")
    else:
        expected = opt.opt_constrained(mu, cov, w_prev=current, tc_bps=10,
                                      risk_aversion=5, bounds=(0, .5), rf=0)
    np.testing.assert_allclose(weights_of(result), expected.reindex(SYMBOLS), atol=1e-6, rtol=0)
    assert weights_of(result).sum() == pytest.approx(1, abs=1e-6)
    assert weights_of(result).between(-1e-6, .500001).all()
    json.dumps(result, allow_nan=False)


def test_frontier_uses_feasible_cap_and_consistent_return_basis(returns, optimized):
    import portlab.optimize as opt
    mu, cov = opt.mean_cov(returns)
    # With 50% cap, maximal return is half of each of the two largest means.
    assert optimized["frontier"]["points"][-1]["return"] == pytest.approx(mu.nlargest(2).mean(), abs=1e-5)
    assert optimized["frontier"]["portfolio"]["return"] == pytest.approx(pd.Series(CURRENT) @ mu)
    assert len(optimized["frontier"]["points"]) == 25
    assert sum(row["optimized_risk"] for row in optimized["weights"]) == pytest.approx(1, abs=1e-6)


def test_turnover_and_cost_units(optimized):
    traded = sum(abs(row["change"]) for row in optimized["weights"])
    assert optimized["turnover"] == pytest.approx(traded / 2)
    assert optimized["estimated_cost"] == pytest.approx(traded * 10 / 10000)


@pytest.mark.parametrize("options", [dict(max_weight=.1), dict(method="bad"), dict(method="black_litterman"), dict(tc_bps=-1)])
def test_invalid_options(returns, options):
    with pytest.raises(OptimizationInputError):
        run_optimization(returns, CURRENT, **options)


def test_short_history_and_missing_weights(returns):
    with pytest.raises(OptimizationInputError, match="60"):
        run_optimization(returns.iloc[:30], CURRENT)
    with pytest.raises(OptimizationInputError, match="weights"):
        run_optimization(returns, {"MCK": 1})


def test_infeasible_engine_output_fails_closed(returns):
    with patch("portlab.optimize.max_sharpe", return_value=pd.Series([1, 0, 0, 0, 0], index=SYMBOLS)):
        with pytest.raises(EngineUnavailableError, match="constraints"):
            run_optimization(returns, CURRENT)


def test_rolling_no_lookahead_and_drift(returns):
    import portlab.optimize as opt
    sample = returns.iloc[:105]
    report = run_rolling_optimization(sample, CURRENT, lookback=60, step=21)
    changed = sample.copy()
    changed.iloc[60:] *= 1.5
    altered = run_rolling_optimization(changed, CURRENT, lookback=60, step=21)
    assert report["rows"][0] == altered["rows"][0]
    first = report["rows"][0]
    mu, cov = opt.mean_cov(sample.iloc[:60])
    direct = opt.gmv(mu, cov, bounds=(0, .5), solver="slsqp")
    np.testing.assert_allclose([first["weights"][s] for s in SYMBOLS], direct.reindex(SYMBOLS), atol=1e-6)
    assert first["training_end"] < first["date"]
    assert first["date"] == str(sample.index[60].date())
    previous = pd.Series(first["weights"]).reindex(SYMBOLS) * (1 + sample.iloc[60:81]).prod()
    previous /= previous.sum()
    second = pd.Series(report["rows"][1]["weights"]).reindex(SYMBOLS)
    assert report["rows"][1]["turnover"] == pytest.approx((second - previous).abs().sum() / 2)


def test_rolling_young_history(returns):
    result = run_rolling_optimization(returns.iloc[:252], CURRENT)
    assert result["young_history"]
    assert result["rows"] == []


@pytest.fixture
def stored_portfolio(db):
    from decimal import Decimal
    from apps.analysis.models import Analysis
    from apps.marketdata.models import Security, PriceHistory
    prices = pd.read_csv(FIXTURE, index_col="date", parse_dates=True)[SYMBOLS]
    for symbol in SYMBOLS:
        security = Security.objects.create(symbol=symbol)
        PriceHistory.objects.bulk_create([
            PriceHistory(security=security, date=day.date(), close=Decimal(str(value)), adj_close=Decimal(str(value)))
            for day, value in prices[symbol].items()
        ])
    return Analysis.objects.create(slug="optimizer-test", input_hash="optimizer-test", engine_version="0.2.2",
        inputs={"holdings": [{"symbol": s, "weight": w} for s, w in CURRENT.items()],
                "start": str(prices.index[0].date()), "end": str(prices.index[-1].date())})


@pytest.mark.django_db
def test_optimizer_web_gate_and_no_market_requests(client, stored_portfolio):
    import portlab.optimize as opt
    from apps.analysis.optimizer import load_optimization_portfolio
    with patch("apps.marketdata.sources.YahooPriceSource.fetch", side_effect=AssertionError("No live prices")):
        response = client.get("/optimize", {"slug": stored_portfolio.slug})
    assert response.status_code == 200
    report = response.context["report"]
    _, cached_returns, _ = load_optimization_portfolio(stored_portfolio.slug)
    mu, cov = opt.mean_cov(cached_returns)
    direct = opt.max_sharpe(mu, cov, rf=0, bounds=(0, .5), solver="slsqp")
    np.testing.assert_allclose(weights_of(report), direct.reindex(SYMBOLS), atol=1e-4, rtol=0)
    assert report["data_vintage"]["end"] == stored_portfolio.inputs["end"]
    assert 'id="chart-frontier"' in response.content.decode()
    assert 'id="chart-risk"' in response.content.decode()
    assert client.session["analysis_slug"] == stored_portfolio.slug
    assert client.get("/optimize").status_code == 200
    json.dumps(response.context["charts"], allow_nan=False)


@pytest.mark.django_db
def test_tool_pages(client, stored_portfolio):
    risk = client.get("/tools/risk-parity", {"slug": stored_portfolio.slug})
    assert risk.status_code == 200
    assert risk.context["report"]["method"] == "risk_parity"
    assert 'id="chart-risk"' in risk.content.decode()
    rolling = client.get("/tools/rolling-optimization", {"slug": stored_portfolio.slug})
    assert rolling.status_code == 200
    assert 'id="chart-rolling"' in rolling.content.decode()
    assert len(rolling.context["report"]["rows"]) > 1
    assert all(row["training_end"] < row["date"] for row in rolling.context["report"]["rows"])


@pytest.mark.django_db
@pytest.mark.parametrize("query, message", [
    ({"cap_percent": "10"}, "cap must allow"),
    ({"method": "bogus"}, "Select a valid choice"),
    ({"cap_percent": "NaN"}, "Enter a number"),
    ({"method": "black_litterman"}, "at least one explicit"),
    ({"method": "black_litterman", "views": "FAKE, 12, 60"}, "Line 1"),
])
def test_invalid_web_options_are_inline(client, stored_portfolio, query, message):
    response = client.get("/optimize", {"slug": stored_portfolio.slug, **query})
    assert response.status_code == 200
    assert message in response.content.decode()
    assert not response.context.get("report")


@pytest.mark.django_db
def test_black_litterman_web(client, stored_portfolio):
    response = client.get("/optimize", {"slug": stored_portfolio.slug, "method": "black_litterman", "views": "MCK, 12, 60"})
    assert response.status_code == 200
    assert response.context["report"]["method"] == "black_litterman"
    assert "not market-cap weights" in response.content.decode()


@pytest.mark.django_db
def test_short_rolling_history_web(client, stored_portfolio):
    from datetime import date
    from apps.marketdata.models import PriceHistory
    dates = list(PriceHistory.objects.values_list("date", flat=True).distinct().order_by("date"))
    stored_portfolio.inputs["end"] = str(dates[100])
    stored_portfolio.save()
    response = client.get("/tools/rolling-optimization", {"slug": stored_portfolio.slug})
    assert response.status_code == 200
    assert response.context["report"]["young_history"]
    assert "253+ daily return observations" in response.content.decode()


@pytest.mark.django_db
def test_missing_analysis_price_and_engine_states(client, stored_portfolio):
    from apps.marketdata.models import PriceHistory
    empty_client = type(client)()
    for path in ("/optimize", "/tools/risk-parity", "/tools/rolling-optimization"):
        assert empty_client.get(path).status_code == 200
        assert empty_client.get(path, {"slug": "missing"}).status_code == 404
    with patch("apps.analysis.optimization_views.optimize_portfolio", side_effect=EngineUnavailableError()):
        assert client.get("/optimize", {"slug": stored_portfolio.slug}).status_code == 503
    PriceHistory.objects.all().delete()
    response = client.get("/optimize", {"slug": stored_portfolio.slug})
    assert response.status_code == 200
    assert "Cached price history is unavailable" in response.content.decode()


def test_forms_reject_nonfinite_and_duplicate_views():
    from apps.analysis.optimization_forms import OptimizationForm
    base = dict(method="black_litterman", cap_percent=50, rf_percent=0, tc_bps=10)
    for views in ("MCK, nan, 60", "MCK, 12, 0", "MCK, 12, 60\nMCK, 10, 30"):
        form = OptimizationForm({**base, "views": views}, symbols=SYMBOLS)
        assert not form.is_valid()
        assert "views" in form.errors


def portfolio_post(slug=""):
    return {"slug": slug, "holdings_json": json.dumps([
        {"symbol": "MCK", "weight": 60}, {"symbol": "LLY", "weight": 40}]),
        "benchmark": "MCK", "start_date": "2022-01-03", "end_date": "2024-12-31",
        "method": "gmv", "cap_percent": 70, "rf_percent": 0, "tc_bps": 10}


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/optimize", "/tools/risk-parity", "/tools/rolling-optimization"])
def test_shared_editor_applies_edits_without_mutating_saved_analysis(client, stored_portfolio, path):
    from apps.analysis.models import Analysis, AnalysisResult
    from apps.marketdata.models import Security
    original = json.loads(json.dumps(stored_portfolio.inputs))
    counts = (Analysis.objects.count(), AnalysisResult.objects.count(), Security.objects.count())
    with patch("apps.marketdata.sources.YahooPriceSource.fetch", side_effect=AssertionError("No market requests")):
        response = client.post(path, portfolio_post(stored_portfolio.slug))
    assert response.status_code == 200
    assert response.context["portfolio_form"].is_valid()
    report = response.context["report"]
    assert report["data_vintage"]["start"] >= "2022-01-03"
    assert report["data_vintage"]["end"] <= "2024-12-31"
    if path.endswith("rolling-optimization"):
        assert report["symbols"] == ["MCK", "LLY"]
    else:
        assert {row["symbol"]: row["current"] for row in report["weights"]} == pytest.approx({"MCK": .6, "LLY": .4})
    stored_portfolio.refresh_from_db()
    assert stored_portfolio.inputs == original
    assert (Analysis.objects.count(), AnalysisResult.objects.count(), Security.objects.count()) == counts
    assert 'data-portfolio-form' in response.content.decode()
    assert '/static/portfolio-input.js' in response.content.decode()


@pytest.mark.django_db
def test_tool_can_start_without_saved_analysis(client, stored_portfolio):
    response = client.post("/optimize", portfolio_post())
    assert response.status_code == 200
    assert response.context["analysis"] is None
    assert response.context["report"]["weights"]


@pytest.mark.django_db
@pytest.mark.parametrize("holdings, error", [
    ([{"symbol": "MCK", "weight": 20}], "Weights sum to"),
    ([{"symbol": "MCK", "weight": float("nan")}], "finite"),
    ([{"symbol": "MCK", "weight": -10}, {"symbol": "MCK", "weight": 110}], "nonnegative"),
    ([{"symbol": "UNKNOWN", "weight": 100}], "UNKNOWN"),
    ([1], "Each holding"),
])
def test_shared_editor_rejects_bad_inputs_inline(client, stored_portfolio, holdings, error):
    from apps.analysis.models import Analysis
    before = Analysis.objects.count()
    payload = portfolio_post(stored_portfolio.slug)
    payload["holdings_json"] = json.dumps(holdings)
    response = client.post("/optimize", payload)
    assert response.status_code == 200
    assert error in response.content.decode()
    assert not response.context.get("report")
    assert Analysis.objects.count() == before


@pytest.mark.django_db
def test_duplicate_holdings_merge_with_notice(client, stored_portfolio):
    payload = portfolio_post(stored_portfolio.slug)
    payload["holdings_json"] = json.dumps([{"symbol":"MCK","weight":30}, {"symbol":"MCK","weight":30}, {"symbol":"LLY","weight":40}])
    response = client.post("/optimize", payload)
    assert response.status_code == 200
    assert "Duplicate tickers merged: MCK" in response.content.decode()
    assert len(response.context["report"]["weights"]) == 2


@pytest.mark.django_db
def test_shared_editor_date_errors(client, stored_portfolio):
    payload = portfolio_post(stored_portfolio.slug)
    payload["end_date"] = "2020-01-01"
    response = client.post("/optimize", payload)
    assert response.status_code == 200
    assert "End date must be after start date" in response.content.decode()
    assert not response.context.get("report")


@pytest.mark.django_db
@pytest.mark.parametrize("path, target, post", [
    ("/optimize?slug=optimizer-test", "apps.analysis.optimization_views.optimize_portfolio", False),
    ("/risk?slug=optimizer-test", "apps.analysis.risklens.get_risklens", False),
    ("/analyze", "apps.analysis.views.analyze", True),
])
def test_engine_errors_have_log_correlated_reference(client, stored_portfolio, caplog, path, target, post):
    secret = "private internal engine detail"
    with patch(target, side_effect=EngineUnavailableError(secret)):
        response = client.post(path, portfolio_post()) if post else client.get(path)
    assert response.status_code == 503
    reference = response.context["error_reference"]
    assert len(reference) == 12
    assert reference in response.content.decode()
    assert reference in caplog.text
    assert secret not in response.content.decode()


def test_drawdown_annotation_identifies_minimum():
    from apps.analysis.charts import drawdown_chart
    # Hand-constructed chart-only values; not a market-data fixture or engine path.
    chart = drawdown_chart(["a", "b", "c"], [0, -.2, -.1], "c")
    marker = chart["series"][0]["markPoint"]["data"][0]
    assert marker["coord"] == ["b", -20]
    assert marker["value"] == -20
    assert drawdown_chart([], [], "c")["series"][0]["markPoint"]["data"] == []
