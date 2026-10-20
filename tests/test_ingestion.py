"""
Unit tests for apps/marketdata/ingestion.py.

Uses pytest-django's `db` fixture so tests run against the test database.
The PriceSource is always mocked — no real network calls are made.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from apps.marketdata.ingestion import ingest_security
from apps.marketdata.models import PriceHistory, Security
from apps.marketdata.sources import UnknownTickerError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_price_df(rows: int = 3, start: str = "2021-01-04") -> pd.DataFrame:
    """Minimal DataFrame matching what YahooPriceSource.fetch returns."""
    idx = [
        date.fromisoformat(d)
        for d in pd.date_range(start, periods=rows, freq="B").strftime("%Y-%m-%d")
    ]
    return pd.DataFrame(
        {
            "open":      [100.0 + i for i in range(rows)],
            "high":      [105.0 + i for i in range(rows)],
            "low":       [95.0 + i for i in range(rows)],
            "close":     [102.0 + i for i in range(rows)],
            "adj_close": [101.0 + i for i in range(rows)],
            "volume":    pd.array([1_000_000 + i * 1000 for i in range(rows)], dtype="Int64"),
        },
        index=idx,
    )


def _mock_source(df: pd.DataFrame) -> MagicMock:
    """Return a PriceSource mock that validates any ticker and returns df."""
    src = MagicMock()
    src.validate.return_value = True
    src.fetch.return_value = df
    return src


def _unknown_source() -> MagicMock:
    """Return a PriceSource mock that rejects every ticker."""
    src = MagicMock()
    src.validate.return_value = False
    return src


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestIngestSecurity:
    def test_creates_security_row(self):
        src = _mock_source(_make_price_df())
        ingest_security("SPY", src)
        assert Security.objects.filter(symbol="SPY").exists()

    def test_symbol_uppercased(self):
        src = _mock_source(_make_price_df())
        ingest_security("spy", src)
        assert Security.objects.filter(symbol="SPY").exists()

    def test_does_not_duplicate_security_row(self):
        src = _mock_source(_make_price_df())
        ingest_security("SPY", src)
        ingest_security("SPY", src)  # second call
        assert Security.objects.filter(symbol="SPY").count() == 1

    def test_creates_price_history_rows(self):
        df = _make_price_df(rows=5)
        src = _mock_source(df)
        ingest_security("AAPL", src)
        security = Security.objects.get(symbol="AAPL")
        assert PriceHistory.objects.filter(security=security).count() == 5

    def test_price_values_stored_correctly(self):
        df = _make_price_df(rows=1)
        src = _mock_source(df)
        ingest_security("MSFT", src)
        security = Security.objects.get(symbol="MSFT")
        row = PriceHistory.objects.get(security=security)
        assert float(row.close) == pytest.approx(102.0)
        assert float(row.adj_close) == pytest.approx(101.0)

    def test_upsert_does_not_duplicate_price_rows(self):
        df = _make_price_df(rows=3)
        src = _mock_source(df)
        ingest_security("GLD", src)
        ingest_security("GLD", src)  # same data again
        security = Security.objects.get(symbol="GLD")
        # Rows should be 3, not 6
        assert PriceHistory.objects.filter(security=security).count() == 3

    def test_refresh_rechecks_full_history_and_reconciles_old_adjustments(self):
        """A dividend revision must update earlier adjusted closes, not just append."""
        df = _make_price_df(rows=3, start="2021-01-04")
        src = _mock_source(df)
        ingest_security("IWM", src)
        revised = df.copy()
        revised.loc[date(2021, 1, 4), "adj_close"] = 90.0
        src.fetch.return_value = revised
        ingest_security("IWM", src)
        assert src.fetch.call_args.args[1] is None  # PriceSource maximum history
        assert PriceHistory.objects.get(security__symbol="IWM", date=date(2021, 1, 4)).adj_close == Decimal('90.0000')

    def test_unknown_ticker_raises_and_does_not_create_row(self):
        src = _unknown_source()
        with pytest.raises(UnknownTickerError):
            ingest_security("XXXX", src)
        assert not Security.objects.filter(symbol="XXXX").exists()

    def test_unknown_ticker_validate_called_before_create(self):
        """validate() must be called before any DB write."""
        src = _unknown_source()
        try:
            ingest_security("ZZZZZ", src)
        except UnknownTickerError:
            pass
        src.validate.assert_called_once_with("ZZZZZ")
        assert not Security.objects.filter(symbol="ZZZZZ").exists()
