"""
Market data source abstraction.

Defines the PriceSource interface and the Yahoo Finance implementation.
All production ingestion goes through this module; the rest of the app
never imports yfinance directly.

Alpha convention note
---------------------
This module is a pure data-fetching layer — it does not interpret alpha
or confidence-level conventions.  See apps/analysis/engine.py for those.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date, timedelta

import pandas as pd

logger = logging.getLogger(__name__)


class UnknownTickerError(Exception):
    """Raised when a ticker cannot be resolved at the data source."""


class PriceSource(ABC):
    """
    Abstract interface for a market-data source.

    Implementations must be stateless and thread-safe (constructed once,
    called many times by the nightly job).
    """

    @abstractmethod
    def validate(self, symbol: str) -> bool:
        """
        Return True if *symbol* is recognised by this source, False otherwise.
        Unknown instruments return False; network failures may propagate.
        """

    @abstractmethod
    def fetch(
        self,
        symbol: str,
        start: date | None,
        end: date,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV history for *symbol* between *start* and *end* (inclusive).
        A None start requests maximum available history. Corporate actions
        are carried in the returned DataFrame.attrs["actions"].

        Returns a DataFrame with columns:
            date (datetime.date), open, high, low, close, adj_close, volume

        The ``date`` column is the index key; ``close`` and ``adj_close``
        are never null.  All price columns are float64; volume is int64
        (nullable via pandas Int64Dtype).

        Raises UnknownTickerError if the source returns no data at all.
        """


# ---------------------------------------------------------------------------
# Yahoo Finance implementation
# ---------------------------------------------------------------------------

_RENAME = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
    # yfinance v0.2 multi-level column names (with Price/Ticker levels)
    # are handled by the _flatten helper below.
}

_REQUIRED_COLUMNS = {"open", "high", "low", "close", "adj_close", "volume"}


def _flatten_yf_columns(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    yfinance ≥ 0.2.38 returns a MultiIndex column header when multiple
    tickers are requested, and sometimes even for single-ticker calls in
    newer versions.  Flatten to the simple column names we need.
    """
    if isinstance(df.columns, pd.MultiIndex):
        # levels: (Price, Ticker) → keep the Price level for our symbol
        df = df.xs(symbol, level="Ticker", axis=1)
    return df


class YahooPriceSource(PriceSource):
    """
    PriceSource backed by yfinance.  Validates a ticker by attempting a
    short fetch; raises UnknownTickerError when yfinance returns no data.
    """

    def validate(self, symbol: str) -> bool:
        try:
            self.fetch(symbol, None, date.today())
            return True
        except UnknownTickerError:
            return False
        except Exception as exc:  # network error etc. — propagate
            logger.warning("validate(%s) unexpected error: %s", symbol, exc)
            raise

    def fetch(
        self,
        symbol: str,
        start: date | None,
        end: date,
    ) -> pd.DataFrame:
        import yfinance as yf  # lazy import: keeps test mocking simple

        window = {"start": start.isoformat()} if start is not None else {"period": "max"}
        raw = yf.download(
            symbol,
            **window,
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=False,
            progress=False,
            actions=True,
        )

        if raw.empty:
            raise UnknownTickerError(f"No data returned for symbol '{symbol}'")

        raw = _flatten_yf_columns(raw, symbol)

        # Rename to our canonical column names
        raw = raw.rename(columns=_RENAME)
        raw.index.name = "date"
        raw.index = raw.index.date  # DatetimeIndex → date objects

        actions = []
        for day, row in raw.iterrows():
            for column, action_type in (("Dividends", "CASH_DIVIDEND"), ("Stock Splits", "SPLIT")):
                value = row.get(column, 0)
                if pd.notna(value) and float(value) != 0:
                    actions.append({"ex_date": day, "action_type": action_type, "ratio": float(value)})

        # Keep only the columns we care about; add any missing optional ones
        df = raw[[c for c in ("open", "high", "low", "close", "adj_close", "volume") if c in raw.columns]].copy()
        for col in ("open", "high", "low", "close", "adj_close"):
            if col not in df.columns:
                df[col] = None
        if "volume" not in df.columns:
            df["volume"] = None

        # Ensure correct dtypes
        for col in ("open", "high", "low", "close", "adj_close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")

        # Drop rows where the required price fields are null
        df = df.dropna(subset=["close", "adj_close"])

        if df.empty:
            raise UnknownTickerError(
                f"All rows for '{symbol}' had null close/adj_close after cleaning"
            )

        df.attrs["actions"] = actions
        return df
