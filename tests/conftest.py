"""
Shared pytest fixtures for the Sentinel test suite.

Conventions:
- Unit tests (no DB): use `mock_source` + plain Python; no Django marks needed.
- Integration tests (DB): mark with @pytest.mark.django_db; use `db_client` or
  Django's `Client` directly.
- No test hits the real network; all PriceSource calls go through mocks.
"""

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from apps.marketdata.sources import PriceSource


# ---------------------------------------------------------------------------
# Price-data fixtures
# ---------------------------------------------------------------------------

def make_price_df(rows: int = 5, start: str = "2021-01-04") -> pd.DataFrame:
    """
    Return a DataFrame in the format that YahooPriceSource.fetch() returns:
      index: datetime.date objects (business days)
      columns: open, high, low, close, adj_close, volume
    """
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


@pytest.fixture
def price_df():
    """A 5-row OHLCV DataFrame for use in unit tests."""
    return make_price_df()


@pytest.fixture
def mock_source(price_df):
    """
    A MagicMock implementing PriceSource that validates any ticker and
    returns `price_df` from fetch().
    """
    src = MagicMock(spec=PriceSource)
    src.validate.return_value = True
    src.fetch.return_value = price_df
    return src


@pytest.fixture
def unknown_source():
    """A PriceSource mock that rejects every ticker."""
    src = MagicMock(spec=PriceSource)
    src.validate.return_value = False
    return src
