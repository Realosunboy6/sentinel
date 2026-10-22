"""M5 production boundary checks."""

import re
import json
from unittest.mock import patch

import pandas as pd
import pytest
from django.test import RequestFactory, override_settings

from apps.core.views import server_error
from apps.analysis.engine import EngineUnavailableError
from apps.marketdata.models import Security


@pytest.mark.django_db
def test_healthz_checks_database(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_healthz_hides_database_failure_details(client):
    with patch("apps.core.views.connection.cursor", side_effect=RuntimeError("secret host")):
        response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert b"secret host" not in response.content


def test_production_security_settings_are_enabled(settings):
    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert "whitenoise.middleware.WhiteNoiseMiddleware" in settings.MIDDLEWARE
    assert settings.PRODUCTION_STATICFILES_BACKEND.endswith(
        "CompressedManifestStaticFilesStorage"
    )
    assert settings.STORAGES["staticfiles"]["BACKEND"].endswith(
        "StaticFilesStorage"
    )


@override_settings(DEBUG=False)
def test_unknown_route_uses_friendly_404(client):
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    assert b"Page not found" in response.content


def test_server_error_returns_safe_log_reference(caplog):
    try:
        raise RuntimeError("private server failure")
    except RuntimeError:
        response = server_error(RequestFactory().get("/failed"))
    body = response.content.decode()
    assert response.status_code == 500
    assert "Request failed" in body
    reference = re.search(r"<strong>([0-9a-f]{12})</strong>", body).group(1)
    assert reference in caplog.text
    assert "private server failure" in caplog.text
    assert "private server failure" not in body


@pytest.mark.django_db
@pytest.mark.parametrize("failure,status", [
    (EngineUnavailableError("private engine detail"), 503),
    (RuntimeError("private runtime detail"), 500),
])
def test_m4_tool_engine_failures_are_safe_and_correlated(client, caplog, failure, status):
    Security.objects.bulk_create([Security(symbol="SPY"), Security(symbol="MCK")])
    index = pd.date_range("2021-01-04", periods=35, freq="B")
    prices = pd.DataFrame({"MCK": range(100, 135), "SPY": range(200, 235)}, index=index)
    payload = {
        "holdings_json": json.dumps([{"symbol": "MCK", "weight": 100}]),
        "benchmark": "SPY",
        "start_date": str(index[0].date()),
        "end_date": str(index[-1].date()),
    }
    effective = [{"symbol": "MCK", "weight": 1.0}]
    with patch("apps.tools.views.prepare_prices", return_value=(effective, prices, [])), \
         patch("apps.tools.views.run_tool_report", side_effect=failure):
        response = client.post("/tools/backtest", payload)
    assert response.status_code == status
    reference = response.context["error_reference"]
    assert reference in response.content.decode()
    assert reference in caplog.text
    assert "private" not in response.content.decode()
