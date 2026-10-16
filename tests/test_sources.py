"""
Unit tests for apps/marketdata/sources.py.

All tests mock yfinance.download — no network calls are made.
"""

from datetime import date
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from apps.marketdata.sources import (
    UnknownTickerError,
    YahooPriceSource,
    _flatten_yf_columns,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(rows: int = 5) -> pd.DataFrame:
    """
    Build a minimal yfinance-style DataFrame with simple (non-MultiIndex)
    columns: Open, High, Low, Close, Adj Close, Volume.
    Indexed by pandas Timestamps (as yfinance returns).
    """
    idx = pd.date_range("2021-01-04", periods=rows, freq="B")
    return pd.DataFrame(
        {
            "Open":      [100.0 + i for i in range(rows)],
            "High":      [105.0 + i for i in range(rows)],
            "Low":       [95.0 + i for i in range(rows)],
            "Close":     [102.0 + i for i in range(rows)],
            "Adj Close": [101.0 + i for i in range(rows)],
            "Volume":    [1_000_000 + i * 1000 for i in range(rows)],
        },
        index=idx,
    )


def _make_multiindex_ohlcv(symbol: str, rows: int = 5) -> pd.DataFrame:
    """
    Build a yfinance-style DataFrame with MultiIndex columns (Price, Ticker).
    This mirrors what yfinance ≥ 0.2.38 sometimes returns for single tickers.
    """
    base = _make_ohlcv(rows)
    base.columns = pd.MultiIndex.from_tuples(
        [(col, symbol) for col in base.columns],
        names=["Price", "Ticker"],
    )
    return base


# ---------------------------------------------------------------------------
# _flatten_yf_columns
# ---------------------------------------------------------------------------

class TestFlattenYfColumns:
    def test_simple_columns_unchanged(self):
        df = _make_ohlcv()
        result = _flatten_yf_columns(df, "SPY")
        assert list(result.columns) == list(df.columns)

    def test_multiindex_flattened(self):
        df = _make_multiindex_ohlcv("SPY")
        result = _flatten_yf_columns(df, "SPY")
        # Should have a flat Index, not a MultiIndex
        assert not isinstance(result.columns, pd.MultiIndex)
        assert "Open" in result.columns


# ---------------------------------------------------------------------------
# YahooPriceSource.fetch
# ---------------------------------------------------------------------------

class TestYahooPriceSourceFetch:
    def test_fetch_normalizes_columns(self):
        """fetch() returns a DataFrame with our canonical lowercase columns."""
        mock_df = _make_ohlcv()
        with patch("yfinance.download", return_value=mock_df):
            src = YahooPriceSource()
            result = src.fetch("SPY", date(2021, 1, 1), date(2021, 1, 31))

        assert set(result.columns) == {"open", "high", "low", "close", "adj_close", "volume"}

    def test_fetch_date_index_is_date_objects(self):
        """The index must contain datetime.date objects, not Timestamps."""
        mock_df = _make_ohlcv()
        with patch("yfinance.download", return_value=mock_df):
            src = YahooPriceSource()
            result = src.fetch("SPY", date(2021, 1, 1), date(2021, 1, 31))

        assert isinstance(result.index[0], date)
        # Must NOT be a pandas Timestamp
        assert type(result.index[0]) is date

    def test_fetch_price_columns_are_float64(self):
        mock_df = _make_ohlcv()
        with patch("yfinance.download", return_value=mock_df):
            src = YahooPriceSource()
            result = src.fetch("SPY", date(2021, 1, 1), date(2021, 1, 31))

        for col in ("open", "high", "low", "close", "adj_close"):
            assert result[col].dtype == "float64", f"{col} should be float64"

    def test_fetch_volume_is_int64(self):
        mock_df = _make_ohlcv()
        with patch("yfinance.download", return_value=mock_df):
            src = YahooPriceSource()
            result = src.fetch("SPY", date(2021, 1, 1), date(2021, 1, 31))

        # pandas Int64Dtype (nullable) or int64 are both acceptable
        assert str(result["volume"].dtype).lower() in ("int64", "int64")

    def test_fetch_empty_raises_unknown_ticker(self):
        """An empty DataFrame from yfinance must raise UnknownTickerError."""
        with patch("yfinance.download", return_value=pd.DataFrame()):
            src = YahooPriceSource()
            with pytest.raises(UnknownTickerError):
                src.fetch("XXXX", date(2021, 1, 1), date(2021, 1, 31))

    def test_fetch_multiindex_columns_handled(self):
        """fetch() handles MultiIndex column DataFrames from newer yfinance."""
        mock_df = _make_multiindex_ohlcv("AAPL")
        with patch("yfinance.download", return_value=mock_df):
            src = YahooPriceSource()
            result = src.fetch("AAPL", date(2021, 1, 1), date(2021, 1, 31))

        assert "close" in result.columns
        assert "adj_close" in result.columns


# ---------------------------------------------------------------------------
# YahooPriceSource.validate
# ---------------------------------------------------------------------------

class TestYahooPriceSourceValidate:
    def test_validate_known_ticker_returns_true(self):
        mock_df = _make_ohlcv()
        with patch("yfinance.download", return_value=mock_df):
            src = YahooPriceSource()
            assert src.validate("SPY") is True

    def test_validate_unknown_ticker_returns_false(self):
        with patch("yfinance.download", return_value=pd.DataFrame()):
            src = YahooPriceSource()
            assert src.validate("XXXX") is False
