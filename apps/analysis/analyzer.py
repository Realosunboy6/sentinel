"""
Analysis orchestrator.

Entry point: analyze(holdings, start_date, end_date, benchmark_symbol)

This module:
1. Validates / ingests unknown tickers on-demand.
2. Loads adjusted prices from price_history, builds simple returns.
3. Canonicalises the input and computes an input_hash.
4. Checks the AnalysisResult cache.
5. On a cache miss: calls engine.run_analysis(), stores the result, creates
   an Analysis row with a base62 slug.
6. Returns (Analysis, metrics_dict).

No portlab import here — that lives exclusively in engine.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from apps.analysis.engine import EngineUnavailableError, run_analysis
from apps.analysis.models import Analysis, AnalysisResult
from apps.marketdata.ingestion import ingest_security
from apps.marketdata.models import PriceHistory, Security
from apps.marketdata.sources import UnknownTickerError, YahooPriceSource

logger = logging.getLogger(__name__)

# Default analysis window per spec §6.
DEFAULT_YEARS = 10
# Maximum forward-fill gap (trading-day holidays are ≤ 3 days; 5 is safe).
MAX_FFILL_DAYS = 5


class InvalidTickerError(Exception):
    """Raised when a ticker cannot be resolved at the data source."""
    def __init__(self, symbol: str):
        self.symbol = symbol
        super().__init__(f"Unknown ticker: {symbol!r}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze(
    holdings: list[dict],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    benchmark_symbol: str = "SPY",
) -> tuple[Analysis, dict]:
    """
    Run (or retrieve from cache) a portfolio analysis.

    Parameters
    ----------
    holdings:
        [{"symbol": "MCK", "weight": 0.2998}, ...]
        Weights are normalised to sum to 1 before hashing and analysis.
    start_date:
        Inclusive start of the analysis window.  Defaults to 10 years ago.
    end_date:
        Inclusive end of the analysis window.  Defaults to today.
    benchmark_symbol:
        Ticker for the benchmark series (default: "SPY").

    Returns
    -------
    (Analysis instance, metrics dict)
    """
    today = date.today()
    if end_date is None:
        end_date = today
    if start_date is None:
        start_date = date(today.year - DEFAULT_YEARS, today.month, today.day)

    # Ensure all symbols (including benchmark) are in the DB.
    all_symbols = [h["symbol"] for h in holdings]
    if benchmark_symbol not in all_symbols:
        all_symbols = all_symbols + [benchmark_symbol]

    _ensure_symbols_ingested(all_symbols)

    # Canonicalise and hash.
    canonical = canonicalize(holdings, start_date, end_date, benchmark_symbol)
    h = input_hash(canonical)

    # Load prices and find the latest available date.
    prices_df = load_prices(all_symbols, start_date, end_date)
    if prices_df.empty:
        raise ValueError("No price data available for the requested date range.")

    latest_date = prices_df.index.max()
    if hasattr(latest_date, "date"):
        latest_date = latest_date.date()

    # Cache check.
    cached = AnalysisResult.objects.filter(
        input_hash=h, data_asof=latest_date
    ).first()

    if cached is not None:
        analysis = Analysis.objects.filter(input_hash=h).order_by("-created_at").first()
        if analysis is None:
            # Cached result exists but the Analysis row was somehow deleted — recreate.
            analysis = _create_analysis(h, canonical)
        return analysis, cached.metrics

    # Cache miss — run the engine.
    port_symbols = [h_["symbol"] for h_ in holdings]
    returns_df = make_returns(prices_df)
    port_returns_df = returns_df[port_symbols]
    bench_returns = returns_df[benchmark_symbol]

    metrics = run_analysis(
        holdings=holdings,
        prices_df=port_returns_df,
        benchmark_returns=bench_returns,
    )

    # Store result and analysis.
    AnalysisResult.objects.create(
        input_hash=h,
        data_asof=latest_date,
        metrics=metrics,
    )
    analysis = _create_analysis(h, canonical)

    return analysis, metrics


# ---------------------------------------------------------------------------
# Supporting functions
# ---------------------------------------------------------------------------

def canonicalize(
    holdings: list[dict],
    start_date: date,
    end_date: date,
    benchmark_symbol: str,
) -> str:
    """
    Produce a stable string representation of the analysis inputs.
    Holdings are sorted by symbol; weights are rounded to 6 dp.
    """
    sorted_holdings = sorted(
        [{"symbol": h["symbol"], "weight": round(float(h["weight"]), 6)} for h in holdings],
        key=lambda x: x["symbol"],
    )
    obj = {
        "holdings": sorted_holdings,
        "start": str(start_date),
        "end": str(end_date),
        "benchmark": benchmark_symbol,
    }
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def input_hash(canonical: str) -> str:
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_prices(
    symbols: list[str],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """
    Query PriceHistory for all symbols, pivot to a wide DataFrame of
    adj_close prices, forward-fill gaps (up to MAX_FFILL_DAYS), and
    return only rows where all columns are present.
    """
    qs = (
        PriceHistory.objects
        .filter(
            security__symbol__in=symbols,
            date__gte=start_date,
            date__lte=end_date,
        )
        .values("security__symbol", "date", "adj_close")
        .order_by("date")
    )
    if not qs.exists():
        return pd.DataFrame()

    df = pd.DataFrame.from_records(qs)
    df["adj_close"] = df["adj_close"].astype(float)
    wide = df.pivot(index="date", columns="security__symbol", values="adj_close")
    wide.index = pd.to_datetime(wide.index)
    wide = wide.sort_index()

    # Forward-fill short gaps (holidays); limit to MAX_FFILL_DAYS.
    wide = wide.ffill(limit=MAX_FFILL_DAYS)

    # Drop rows that are still missing any symbol.
    wide = wide.dropna()

    return wide


def make_returns(prices_df: pd.DataFrame) -> pd.DataFrame:
    """Simple percentage returns; first row is dropped (NaN)."""
    return prices_df.pct_change().dropna()


def gen_slug(length: int = 8) -> str:
    """
    Generate a URL-safe base62-ish slug using secrets.token_urlsafe.
    Re-rolls until it is unique in the analyses table.
    Spec §6: ≥ 6 chars.
    """
    assert length >= 6
    while True:
        candidate = secrets.token_urlsafe(length)[:length]
        if not Analysis.objects.filter(slug=candidate).exists():
            return candidate


def _ensure_symbols_ingested(symbols: list[str]) -> None:
    """
    For each symbol not yet in the securities table, attempt to ingest it.
    Raises InvalidTickerError if a symbol cannot be resolved.
    """
    source = YahooPriceSource()
    known = set(Security.objects.filter(symbol__in=symbols).values_list("symbol", flat=True))
    for symbol in symbols:
        if symbol not in known:
            try:
                ingest_security(symbol, source)
            except UnknownTickerError:
                raise InvalidTickerError(symbol)


def _create_analysis(h: str, canonical: str) -> Analysis:
    import portlab
    engine_version = getattr(portlab, "__version__", "unknown")

    return Analysis.objects.create(
        slug=gen_slug(),
        input_hash=h,
        inputs=json.loads(canonical),
        engine_version=engine_version,
    )
