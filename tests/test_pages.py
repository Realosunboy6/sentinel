"""
Smoke tests for Sentinel pages (M0 gate).

These tests use pytest-django's test client and verify that each route
returns HTTP 200 and contains the expected content.  No real price data
is fetched; the securities table may be empty.
"""

import pytest
from django.test import Client


@pytest.fixture
def client():
    return Client()


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
