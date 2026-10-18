"""
Smoke tests for Sentinel pages (M0 + M1 gate).

These tests use pytest-django's test client and verify that each route
returns HTTP 200 (or an expected redirect) and contains the expected content.
No real price data is fetched from the network; the securities table may be
empty for M0 tests.  M1 page tests use the committed K5 price fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
from django.test import Client

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client():
    return Client()


# ---------------------------------------------------------------------------
# M0 gate pages
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSecuritiesPage:
    def test_securities_list_returns_200(self, client):
        response = client.get("/securities/")
        assert response.status_code == 200

    def test_securities_list_contains_heading(self, client):
        response = client.get("/securities/")
        content = response.content.decode()
        assert "Tracked Securities" in content

    def test_securities_list_empty_state_message(self, client):
        """With no securities in the DB the page shows the seed command hint."""
        response = client.get("/securities/")
        content = response.content.decode()
        assert "refresh_prices" in content

    def test_admin_root_returns_200(self, client):
        """The admin login page must be reachable."""
        response = client.get("/admin/")
        # Admin redirects to login when not authenticated — both 200 and 302 are fine.
        assert response.status_code in (200, 302)


# ---------------------------------------------------------------------------
# M1 gate pages
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLandingPage:
    def test_landing_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_landing_contains_brand(self, client):
        content = client.get("/").content.decode()
        assert "Sentinel" in content

    def test_landing_contains_analyze_link(self, client):
        content = client.get("/").content.decode()
        assert "/analyze" in content


@pytest.mark.django_db
class TestAnalyzePage:
    def test_analyze_get_returns_200(self, client):
        response = client.get("/analyze")
        assert response.status_code == 200

    def test_analyze_contains_form(self, client):
        content = client.get("/analyze").content.decode()
        assert "analyze-form" in content

    def test_analyze_preset_prefill(self, client):
        """GET /analyze?preset=k5-sample fills the form (preset must exist)."""
        from apps.analysis.models import Preset
        Preset.objects.get_or_create(
            slug="k5-sample",
            defaults={
                "name": "K5 Sample",
                "inputs": {
                    "holdings": [
                        {"symbol": "MCK", "weight": 0.2998},
                        {"symbol": "LLY", "weight": 0.2355},
                        {"symbol": "PWR", "weight": 0.1906},
                        {"symbol": "NVDA", "weight": 0.1561},
                        {"symbol": "STX", "weight": 0.1180},
                    ],
                    "settings": {"benchmark": "SPY"},
                },
            },
        )
        response = client.get("/analyze?preset=k5-sample")
        assert response.status_code == 200
        content = response.content.decode()
        assert "K5 Sample" in content


@pytest.mark.django_db
class TestAnalyzePost:
    """
    POST /analyze with a valid K5 payload.  We mock the engine call so the
    test does not require a live DB with price history.
    """

    def _k5_post_data(self):
        holdings = [
            {"symbol": "MCK", "weight": 29.98},
            {"symbol": "LLY", "weight": 23.55},
            {"symbol": "PWR", "weight": 19.06},
            {"symbol": "NVDA", "weight": 15.61},
            {"symbol": "STX", "weight": 11.80},
        ]
        return {
            "holdings_json": json.dumps(holdings),
            "benchmark": "SPY",
            "start_date": "2021-01-04",
            "action": "analyze",
        }

    def test_post_with_mocked_engine_redirects(self, client):
        """A valid POST with a mocked analysis redirects to /a/<slug>."""
        import apps.analysis.views as views_mod
        from apps.analysis.models import Analysis, AnalysisResult
        import datetime

        # Load actual golden metrics so the redirect target can render
        golden = json.loads((FIXTURES / "k5_golden.json").read_text())

        def fake_analyze(holdings, start_date=None, end_date=None, benchmark_symbol="SPY"):
            # Create a real Analysis + AnalysisResult in the test DB
            from apps.analysis.analyzer import gen_slug
            analysis = Analysis.objects.create(
                slug=gen_slug(),
                input_hash="testhash",
                inputs={"holdings": holdings},
                engine_version="test",
            )
            AnalysisResult.objects.create(
                input_hash="testhash",
                data_asof=datetime.date(2026, 10, 16),
                metrics=golden,
            )
            return analysis, golden

        with patch("apps.analysis.views.analyze", side_effect=fake_analyze):
            response = client.post("/analyze", self._k5_post_data())

        assert response.status_code == 302
        assert response["Location"].startswith("/a/")

    def test_shared_analysis_returns_200(self, client):
        """GET /a/<slug> returns 200 with chart payloads for a stored analysis."""
        import datetime
        from apps.analysis.models import Analysis, AnalysisResult
        from apps.analysis.analyzer import gen_slug

        golden = json.loads((FIXTURES / "k5_golden.json").read_text())

        analysis = Analysis.objects.create(
            slug=gen_slug(),
            input_hash="testhash2",
            inputs={
                "holdings": [
                    {"symbol": "MCK", "weight": 0.2998},
                    {"symbol": "LLY", "weight": 0.2355},
                    {"symbol": "PWR", "weight": 0.1906},
                    {"symbol": "NVDA", "weight": 0.1561},
                    {"symbol": "STX", "weight": 0.1180},
                ]
            },
            engine_version="test",
        )
        AnalysisResult.objects.create(
            input_hash="testhash2",
            data_asof=datetime.date(2026, 10, 16),
            metrics=golden,
        )

        response = client.get(f"/a/{analysis.slug}")
        assert response.status_code == 200
        content = response.content.decode()
        # CAGR from golden (52.9%), displayed via pct filter → "52.9"
        assert "52." in content  # CAGR percentage present

    def test_shared_analysis_contains_share_url(self, client):
        """The shared analysis page must show the share disclaimer (spec §10)."""
        import datetime
        from apps.analysis.models import Analysis, AnalysisResult
        from apps.analysis.analyzer import gen_slug

        golden = json.loads((FIXTURES / "k5_golden.json").read_text())
        analysis = Analysis.objects.create(
            slug=gen_slug(),
            input_hash="testhash3",
            inputs={"holdings": []},
            engine_version="test",
        )
        AnalysisResult.objects.create(
            input_hash="testhash3",
            data_asof=datetime.date(2026, 10, 16),
            metrics=golden,
        )
        response = client.get(f"/a/{analysis.slug}")
        content = response.content.decode()
        assert "anyone with this link" in content.lower()


@pytest.mark.django_db
class TestTickersAutocomplete:
    def test_returns_200_json(self, client):
        response = client.get("/api/tickers?q=SP")
        assert response.status_code == 200
        assert response["Content-Type"].startswith("application/json")

    def test_empty_query_returns_empty_list(self, client):
        response = client.get("/api/tickers?q=")
        data = json.loads(response.content)
        assert data == []

    def test_returns_known_ticker(self, client):
        """If SPY is in the securities table, autocomplete finds it."""
        from apps.marketdata.models import Security
        Security.objects.get_or_create(
            symbol="SPY", exchange="",
            defaults={"name": "SPDR S&P 500 ETF", "asset_type": "etf"},
        )
        response = client.get("/api/tickers?q=SP")
        data = json.loads(response.content)
        symbols = [d["symbol"] for d in data]
        assert "SPY" in symbols
