"""
Analysis orchestrator.

Entry point: analyze(holdings, start_date, end_date, benchmark_symbol)

This module:
1. Validates cached tickers; requests never ingest data.
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
from datetime import date
from calendar import monthrange
from typing import Optional

import pandas as pd
from django.db import transaction

from apps.analysis.engine import EngineUnavailableError, run_analysis, engine_version
from apps.analysis.models import Analysis, AnalysisResult
from apps.marketdata.models import PriceHistory, Security

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

@transaction.atomic
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
        year = today.year - DEFAULT_YEARS
        start_date = today.replace(year=year, day=min(today.day, monthrange(year, today.month)[1]))

    # Ensure all symbols (including benchmark) are in the DB.
    all_symbols = [h["symbol"] for h in holdings]
    if benchmark_symbol not in all_symbols:
        all_symbols = all_symbols + [benchmark_symbol]

    _ensure_symbols_cached(all_symbols)
    # Match refresh locks and serialize identical cache fills on PostgreSQL.
    list(Security.objects.select_for_update().filter(symbol__in=all_symbols).order_by("pk"))

    # Canonicalise and hash.
    canonical = canonicalize(holdings, start_date, end_date, benchmark_symbol)
    h = input_hash(canonical)

    # Load prices and find the latest available date.
    holdings, prices_df, warnings = prepare_prices(holdings, start_date, end_date, benchmark_symbol)
    signature = hashlib.sha256(("report-v2:" + canonical + prices_df.to_json(date_format="iso")).encode()).hexdigest()

    latest_date = prices_df.index.max()
    if hasattr(latest_date, "date"):
        latest_date = latest_date.date()

    # Cache check.
    cached = AnalysisResult.objects.filter(
        input_hash=h, data_asof=latest_date
    ).first()

    if cached is not None and cached.metrics.get("_input_signature") == signature:
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

    metrics["warnings"] = warnings
    metrics["effective_holdings"] = holdings
    metrics["_input_signature"] = signature
    # Revisions and adapter fixes expire derived results; saved inputs/slugs survive.
    AnalysisResult.objects.filter(input_hash=h, data_asof=latest_date).delete()
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
    total = sum(float(item["weight"]) for item in holdings)
    if total <= 0:
        raise ValueError("Portfolio weights must have a positive sum.")
    sorted_holdings = sorted(
        [{"symbol": h["symbol"].strip().upper(), "weight": round(float(h["weight"]) / total, 6)} for h in holdings],
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
    strict: bool = True,
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
    if strict:
        complete = wide.dropna()
        if not complete.empty and wide.loc[complete.index.min():complete.index.max()].isna().any().any():
            raise ValueError("Cached history has a gap longer than five observations; refresh before analyzing.")
        wide = complete
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


def _ensure_symbols_cached(symbols: list[str]) -> None:
    """Check the local universe, never contact a source."""
    known = set(Security.objects.filter(symbol__in=symbols).values_list('symbol', flat=True))
    for symbol in symbols:
        if symbol not in known:
            raise InvalidTickerError(symbol)


def prepare_prices(holdings, start, end, benchmark=None):
    """Exclude unavailable/stale holdings explicitly and disclose renormalization."""
    symbols = [h['symbol'] for h in holdings]
    requested = list(dict.fromkeys(symbols + ([benchmark] if benchmark else [])))
    wide = load_prices(requested, start, end, strict=False)
    if wide.empty:
        raise ValueError('Cached price history is unavailable in this date range.')
    latest = wide.index.max()
    excluded = []
    for symbol in symbols:
        if symbol not in wide or wide[symbol].last_valid_index() is None:
            excluded.append(symbol)
        elif pd.isna(wide[symbol].iloc[-1]) or (pd.Timestamp(end) - wide[symbol].last_valid_index()).days > 10:
            excluded.append(symbol)
    retained = [h.copy() for h in holdings if h['symbol'] not in excluded]
    if not retained or sum(h['weight'] for h in retained) <= 0:
        raise ValueError('No usable holdings remain: ' + ', '.join(excluded) + '. Refresh cached history or choose an earlier end date.')
    if benchmark and (benchmark not in wide or pd.isna(wide[benchmark].iloc[-1]) or (pd.Timestamp(end) - wide[benchmark].last_valid_index()).days > 10):
        raise ValueError(f'Benchmark {benchmark} has no recent cached prices for this range.')
    total = sum(h['weight'] for h in retained)
    retained = [{**h, 'weight': h['weight'] / total} for h in retained]
    columns = list(dict.fromkeys([h['symbol'] for h in retained] + ([benchmark] if benchmark else [])))
    wide = wide[columns]
    complete = wide.dropna()
    if len(complete) < 2:
        raise ValueError('At least two aligned cached prices are needed.')
    if wide.loc[complete.index.min():complete.index.max()].isna().any().any():
        raise ValueError('Cached history has a gap longer than five observations; refresh before analyzing.')
    warnings = []
    if excluded:
        warnings.append('Excluded unavailable or stale holdings: ' + ', '.join(excluded) + '. Remaining weights were renormalized to 100%.')
    complete.attrs['warnings'] = warnings
    complete.attrs['holdings'] = retained
    return retained, complete, warnings


def _create_analysis(h: str, canonical: str) -> Analysis:
    return Analysis.objects.create(
        slug=gen_slug(),
        input_hash=h,
        inputs=json.loads(canonical),
        engine_version=engine_version(),
    )
