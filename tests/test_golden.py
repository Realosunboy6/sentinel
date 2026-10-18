"""
Golden-number regression test for the portlab engine adapter.

Construction (per ruling 2026-10-16 / spec §13 amendment):
  - Fixture:    tests/fixtures/k5_prices.csv  (committed, never regenerated silently)
  - Method:     adjusted close, daily constant-mix returns (pct_change)
  - Window:     2021-01-04 to 2026-10-16  (1,454 trading days after dropna)
  - Weights:    MCK 0.2998, LLY 0.2355, PWR 0.1906, NVDA 0.1561, STX 0.1180
  - Benchmark:  SPY (same fixture)
  - rf:         0.0  (risk-free rate passed to portlab.metrics.sharpe/sortino)
  - Expected:   tests/fixtures/k5_golden.json  (recorded from portlab 0.2.2)

Independent cross-check (owner, 2026-10-16):
  CAGR 52.76%, vol 20.77%, Sharpe 2.150, max DD −15.30%,
  2021 +77.32%, 2022 +8.67%, VaR95 1.933%

STOP-AND-REPORT RULE (LOCKED):
  If any assertion fails, do not edit the expected value.
  Stop and report: test name, produced value, expected value, delta.
  Then investigate the adapter before touching this file.

metrics.json in docs/design/snippets/ is a DESIGN MOCK (never real price history).
Do not gate on it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from apps.analysis.engine import run_analysis

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN   = json.loads((FIXTURES / "k5_golden.json").read_text())

PORT_SYMS = ["MCK", "LLY", "PWR", "NVDA", "STX"]
HOLDINGS = [
    {"symbol": "MCK",  "weight": 0.2998},
    {"symbol": "LLY",  "weight": 0.2355},
    {"symbol": "PWR",  "weight": 0.1906},
    {"symbol": "NVDA", "weight": 0.1561},
    {"symbol": "STX",  "weight": 0.1180},
]


@pytest.fixture(scope="module")
def engine_result():
    df = pd.read_csv(FIXTURES / "k5_prices.csv", index_col="date", parse_dates=True)
    df.index = df.index.date
    prices = df[PORT_SYMS + ["SPY"]].pct_change().dropna()
    return run_analysis(HOLDINGS, prices[PORT_SYMS], prices["SPY"])


# ---------------------------------------------------------------------------
# Portfolio-level metrics  (tolerance: 1e-4 relative)
# Source: tests/fixtures/k5_golden.json → portfolio
# ---------------------------------------------------------------------------

class TestPortfolioMetrics:
    def test_cagr(self, engine_result):
        # Source: k5_golden.json; owner cross-check: 52.76%
        assert engine_result["portfolio"]["cagr"] == pytest.approx(
            GOLDEN["portfolio"]["cagr"], rel=1e-4
        )

    def test_vol(self, engine_result):
        # Source: k5_golden.json; owner cross-check: 20.77%
        assert engine_result["portfolio"]["vol"] == pytest.approx(
            GOLDEN["portfolio"]["vol"], rel=1e-4
        )

    def test_sharpe(self, engine_result):
        # Source: k5_golden.json; owner cross-check: 2.150 (rf=0.0)
        assert engine_result["portfolio"]["sharpe"] == pytest.approx(
            GOLDEN["portfolio"]["sharpe"], rel=1e-4
        )

    def test_sortino(self, engine_result):
        # Source: k5_golden.json (rf=0.0)
        assert engine_result["portfolio"]["sortino"] == pytest.approx(
            GOLDEN["portfolio"]["sortino"], rel=1e-4
        )

    def test_max_drawdown(self, engine_result):
        # Source: k5_golden.json; owner cross-check: −15.30%
        assert engine_result["portfolio"]["maxdd"] == pytest.approx(
            GOLDEN["portfolio"]["maxdd"], rel=1e-4
        )

    def test_end_value(self, engine_result):
        # Source: k5_golden.json; $10,000 starting value
        assert engine_result["portfolio"]["end"] == pytest.approx(
            GOLDEN["portfolio"]["end"], rel=1e-4
        )


# ---------------------------------------------------------------------------
# Annual returns  (tolerance: 1e-4 relative)
# Source: tests/fixtures/k5_golden.json → annual
# ---------------------------------------------------------------------------

class TestAnnualReturns:
    @pytest.mark.parametrize("year", ["2021", "2022", "2023", "2024", "2025", "2026"])
    def test_annual_return(self, engine_result, year):
        # Source: k5_golden.json; owner cross-check: 2021 +77.32%, 2022 +8.67%
        assert engine_result["annual"][year] == pytest.approx(
            GOLDEN["annual"][year], rel=1e-4
        )


# ---------------------------------------------------------------------------
# VaR / ES  (tolerance: 1e-4 relative)
# Source: tests/fixtures/k5_golden.json
# VaR sign convention: positive number = loss (spec §5.2)
# ---------------------------------------------------------------------------

class TestVaR:
    def test_var95(self, engine_result):
        # Source: k5_golden.json; owner cross-check: VaR95 1.933%
        assert engine_result["var95"] == pytest.approx(GOLDEN["var95"], rel=1e-4)
        assert engine_result["var95"] > 0, "VaR must be a positive loss magnitude (spec §5.2)"

    def test_var99(self, engine_result):
        # Source: k5_golden.json
        assert engine_result["var99"] == pytest.approx(GOLDEN["var99"], rel=1e-4)
        assert engine_result["var99"] > engine_result["var95"], "VaR99 must exceed VaR95"

    def test_es95(self, engine_result):
        # Source: k5_golden.json
        assert engine_result["es95"] == pytest.approx(GOLDEN["es95"], rel=1e-4)
        assert engine_result["es95"] > engine_result["var95"], "ES must exceed VaR at same confidence"


# ---------------------------------------------------------------------------
# Per-asset metrics  (tolerance: 1e-3 relative — slightly looser than portfolio)
# Source: tests/fixtures/k5_golden.json → per_asset
# ---------------------------------------------------------------------------

class TestPerAsset:
    @pytest.mark.parametrize("sym", ["MCK", "LLY", "PWR", "NVDA", "STX"])
    def test_cagr(self, engine_result, sym):
        assert engine_result["per_asset"][sym]["cagr"] == pytest.approx(
            GOLDEN["per_asset"][sym]["cagr"], rel=1e-3
        )

    @pytest.mark.parametrize("sym", ["MCK", "LLY", "PWR", "NVDA", "STX"])
    def test_vol(self, engine_result, sym):
        assert engine_result["per_asset"][sym]["vol"] == pytest.approx(
            GOLDEN["per_asset"][sym]["vol"], rel=1e-3
        )

    @pytest.mark.parametrize("sym", ["MCK", "LLY", "PWR", "NVDA", "STX"])
    def test_sharpe(self, engine_result, sym):
        assert engine_result["per_asset"][sym]["sharpe"] == pytest.approx(
            GOLDEN["per_asset"][sym]["sharpe"], rel=1e-3
        )

    @pytest.mark.parametrize("sym", ["MCK", "LLY", "PWR", "NVDA", "STX"])
    def test_max_drawdown(self, engine_result, sym):
        assert engine_result["per_asset"][sym]["maxdd"] == pytest.approx(
            GOLDEN["per_asset"][sym]["maxdd"], rel=1e-3
        )

    @pytest.mark.parametrize("sym", ["MCK", "LLY", "PWR", "NVDA", "STX"])
    def test_end_value(self, engine_result, sym):
        assert engine_result["per_asset"][sym]["end"] == pytest.approx(
            GOLDEN["per_asset"][sym]["end"], rel=1e-3
        )


# ---------------------------------------------------------------------------
# Benchmark metrics  (tolerance: 1e-4 relative)
# Source: tests/fixtures/k5_golden.json → benchmark
# ---------------------------------------------------------------------------

class TestBenchmarkMetrics:
    def test_cagr(self, engine_result):
        assert engine_result["benchmark"]["cagr"] == pytest.approx(
            GOLDEN["benchmark"]["cagr"], rel=1e-4
        )

    def test_vol(self, engine_result):
        assert engine_result["benchmark"]["vol"] == pytest.approx(
            GOLDEN["benchmark"]["vol"], rel=1e-4
        )

    def test_sharpe(self, engine_result):
        assert engine_result["benchmark"]["sharpe"] == pytest.approx(
            GOLDEN["benchmark"]["sharpe"], rel=1e-4
        )

    def test_max_drawdown(self, engine_result):
        assert engine_result["benchmark"]["maxdd"] == pytest.approx(
            GOLDEN["benchmark"]["maxdd"], rel=1e-4
        )
