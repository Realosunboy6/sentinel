"""M2 gates using committed real prices; no live data or revised anchors."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import json

import pandas as pd
import pytest

from apps.analysis.engine import EngineUnavailableError, run_risklens
from apps.analysis.models import Analysis
from apps.marketdata.models import PriceHistory, Security

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def spy_returns():
    prices = pd.read_csv(FIXTURES / "spy_prices.csv", index_col="date", parse_dates=True)
    return prices.SPY.pct_change().dropna().loc["2019-01-10":]


@pytest.fixture(scope="module")
def report(spy_returns):
    return run_risklens(spy_returns)


def assert_anchors(report):
    # Sources: locked spec §5.6 and existing tests/test_spy_anchors.py.
    bt = report["backtest"]
    assert bt["n_scored"] == 1703
    assert bt["n_exceptions"] == 86
    assert bt["kupiec_lr"] == pytest.approx(0.009, abs=0.001)
    assert [bt[f"chris_n{k}"] for k in ("00", "01", "10", "11")] == [1542, 74, 74, 12]
    assert bt["chris_lr"] == pytest.approx(10.589773, abs=1e-5)
    assert bt["joint_lr"] == pytest.approx(10.5987, abs=0.001)


def test_spy_adapter_anchors(report):
    assert_anchors(report)
    json.dumps(report, allow_nan=False)


def test_basel_uses_99_percent_latest_250(spy_returns, report):
    import portlab.risk.var as var
    import portlab.risk.backtest as bt
    exc = bt.exceptions(spy_returns, var.historical_var(spy_returns, alpha=.01, window=250)).dropna().iloc[-250:]
    expected = bt.basel_traffic_light(int(exc.sum()), n_obs=250, alpha=.01)
    assert report["backtest"]["basel_n_exceptions"] == int(exc.sum())
    assert report["backtest"]["basel_n_scored"] == 250
    assert report["basel_zone"] == expected["zone"]


def test_regime_and_loss_tail_match_engine(spy_returns, report):
    import portlab.risk.regime as regime
    import portlab.risk.tail as tail
    expected = regime.regime_var(spy_returns)
    assert report["regime"]["calm_var95"] == pytest.approx(expected["calm_var"])
    assert report["regime"]["stressed_var95"] == pytest.approx(expected["stressed_var"])
    k = int(len(spy_returns) ** .5)
    assert report["tail"]["hill"] == pytest.approx(tail.hill_estimator(-spy_returns, k)["xi"])


@pytest.mark.parametrize("length", [2, 30, 300])
def test_young_history(spy_returns, length):
    result = run_risklens(spy_returns.iloc[:length])
    assert result["backtest"]["young_history"]
    assert result["backtest"]["kupiec_lr"] is None
    json.dumps(result, allow_nan=False)


def test_garch_failure_is_not_historical(report, spy_returns):
    with patch("portlab.risk.var.garch_var", side_effect=RuntimeError("fit failed")):
        result = run_risklens(spy_returns)
    assert result["var_table"][-1]["var95"] is None
    assert result["var_table"][-1]["var99"] is None


def test_var_sign_on_spy_fixture(report):
    for row in report["var_table"]:
        for key in ("var95", "var99", "es95"):
            assert row[key] is None or row[key] > 0


def test_final_forecast_preserves_expanding_alignment(spy_returns):
    import portlab.risk.var as var
    sample = spy_returns.iloc[:12]
    result = run_risklens(sample)
    # Same pinned public engine, full expanding path vs final-window path.
    for row, function in zip(result["var_table"][:4],
            (var.historical_var, var.parametric_var, var.parametric_var_t, var.cornish_fisher_var)):
        assert row["var95"] == pytest.approx(function(sample, alpha=.05).iloc[-1])


def test_historical_stress_uses_observed_episode(spy_returns, report):
    row = report["stress_scenarios"][0]
    # Direct compounded returns after the baseline close through episode end.
    expected = (1 + spy_returns.loc["2020-02-20":"2020-03-23"]).prod() - 1
    assert row["return"] == pytest.approx(expected)
    assert run_risklens(spy_returns.iloc[-30:])["stress_scenarios"][0]["return"] is None


def seed_prices(prices):
    for symbol in prices.columns:
        security = Security.objects.create(symbol=symbol)
        PriceHistory.objects.bulk_create([
            PriceHistory(security=security, date=day.date(), close=Decimal(str(value)), adj_close=Decimal(str(value)))
            for day, value in prices[symbol].items()
        ])


def create_analysis(holdings, start, end):
    return Analysis.objects.create(slug="risk-test", input_hash="risk-test", engine_version="0.2.2",
        inputs={"holdings": holdings, "start": start, "end": end, "benchmark": "SPY"})


@pytest.mark.django_db
def test_spy_anchors_through_database_and_web(client):
    prices = pd.read_csv(FIXTURES / "spy_prices.csv", index_col="date", parse_dates=True)
    # Include the prior price so pct_change reproduces the locked return start.
    window = prices.loc[:"2019-01-10"].iloc[-2:]
    prices = prices.loc[window.index[0]:]
    seed_prices(prices)
    analysis = create_analysis([{"symbol": "SPY", "weight": 1}], str(prices.index[0].date()), str(prices.index[-1].date()))
    response = client.get("/risk", {"slug": analysis.slug})
    assert response.status_code == 200
    assert_anchors(response.context["risk"])
    for chart in ("histogram", "regime", "drawdown"):
        assert f'id="chart-{chart}"' in response.content.decode()
    charts = json.loads(response.context["charts_json"])
    assert charts["histogram"]["xAxis"]["type"] == "value"
    assert isinstance(charts["histogram"]["series"][0]["markLine"]["data"][0]["xAxis"], float)


@pytest.mark.django_db
def test_k5_report_and_stored_date_range(client):
    prices = pd.read_csv(FIXTURES / "k5_prices.csv", index_col="date", parse_dates=True)
    seed_prices(prices)
    holdings = [{"symbol": s, "weight": w} for s, w in zip(
        ["MCK", "LLY", "PWR", "NVDA", "STX"], [.2998, .2355, .1906, .1561, .1180])]
    end = str(prices.index[-10].date())
    analysis = create_analysis(holdings, str(prices.index[0].date()), end)
    response = client.get("/risk", {"slug": analysis.slug})
    assert response.status_code == 200
    assert response.context["risk"]["data_vintage"]["end"] == end
    assert len(response.context["risk"]["var_table"]) == 5
    assert client.session["analysis_slug"] == analysis.slug
    assert client.get("/risk").status_code == 200


@pytest.mark.django_db
def test_short_history_page(client):
    prices = pd.read_csv(FIXTURES / "spy_prices.csv", index_col="date", parse_dates=True).iloc[-31:]
    seed_prices(prices)
    analysis = create_analysis([{"symbol": "SPY", "weight": 1}], str(prices.index[0].date()), str(prices.index[-1].date()))
    response = client.get("/risk", {"slug": analysis.slug})
    assert response.status_code == 200
    assert "Backtests need 250+ scored observations" in response.content.decode()
    assert "NaN" not in response.context["charts_json"]


@pytest.mark.django_db
def test_missing_analysis_and_engine(client):
    assert client.get("/risk").status_code == 200
    assert client.get("/risk?slug=missing").status_code == 404
    with patch("apps.analysis.risklens.get_risklens", side_effect=EngineUnavailableError("unavailable")):
        assert client.get("/risk?slug=existing").status_code == 503


@pytest.mark.django_db
def test_missing_prices_fail_closed(client):
    analysis = create_analysis([{"symbol": "SPY", "weight": 1}], "2021-01-01", "2026-10-16")
    assert client.get("/risk", {"slug": analysis.slug}).status_code == 503
