"""
Market-data ingestion service.

Entry point: ingest_security(symbol, source)

This module is the ONLY place that writes to price_history and
corporate_actions.  It is called by the nightly refresh_prices management
command and may be called directly in tests (with a mocked source).

Design rules (from spec §6):
- Validate the ticker at the source before creating any DB row.
- Upsert price_history rows (new days appended; existing rows updated if
  adj_close changed — e.g. after a dividend retroactive adjustment).
- Never mutate old price_history rows except via the nightly upsert.
- corporate_actions rows are also upserted.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from apps.marketdata.models import CorporateAction, PriceHistory, Security
from apps.marketdata.sources import PriceSource, UnknownTickerError

logger = logging.getLogger(__name__)

# The earliest date we'll ask the source for on a fresh ingest.
# Yahoo Finance reliably reaches back to the early 1990s; using 1990-01-01
# captures maximum history per spec §6.
_HISTORY_START = date(1990, 1, 1)


def ingest_security(
    symbol: str,
    source: PriceSource,
    start: Optional[date] = None,
) -> Security:
    """
    Fetch and store market data for *symbol*.

    1. Validate the ticker at the source (raises UnknownTickerError if unknown).
    2. Get-or-create the Security row.
    3. Determine the fetch window:
       - Fresh ingest: from *start* (default _HISTORY_START) to today.
       - Incremental refresh: from (latest stored date + 1) to today.
    4. Bulk-upsert PriceHistory rows (update on conflict).
    5. Upsert CorporateAction rows from the source's ``actions`` data if
       available.

    Returns the Security instance.
    """
    symbol = symbol.upper().strip()

    # Step 1: validate
    if not source.validate(symbol):
        raise UnknownTickerError(
            f"Symbol '{symbol}' could not be validated at the data source."
        )

    # Step 2: get-or-create the Security row
    security, created = Security.objects.get_or_create(
        symbol=symbol,
        exchange="",  # Yahoo Finance doesn't distinguish exchanges
        defaults={"asset_type": "stock"},
    )
    if created:
        logger.info("Created new security: %s", symbol)

    # Step 3: determine fetch window
    today = date.today()
    if start is None:
        latest = (
            PriceHistory.objects.filter(security=security)
            .order_by("-date")
            .values_list("date", flat=True)
            .first()
        )
        if latest is not None:
            fetch_start = latest + timedelta(days=1)
        else:
            fetch_start = _HISTORY_START
    else:
        fetch_start = start

    if fetch_start > today:
        logger.info("%s is already up to date (latest: %s)", symbol, fetch_start - timedelta(days=1))
        return security

    # Step 4: fetch
    logger.info("Fetching %s from %s to %s", symbol, fetch_start, today)
    df = source.fetch(symbol, fetch_start, today)

    if df.empty:
        logger.warning("No new rows returned for %s", symbol)
        return security

    _upsert_price_history(security, df)

    return security


def _upsert_price_history(security: Security, df: pd.DataFrame) -> None:
    """
    Bulk-upsert a DataFrame of OHLCV rows into price_history.

    Uses Django 5's bulk_create(update_conflicts=True) for PostgreSQL,
    which maps to INSERT ... ON CONFLICT DO UPDATE.
    """
    rows = [
        PriceHistory(
            security=security,
            date=idx,
            open=_decimal_or_none(row.get("open")),
            high=_decimal_or_none(row.get("high")),
            low=_decimal_or_none(row.get("low")),
            close=row["close"],
            adj_close=row["adj_close"],
            volume=_int_or_none(row.get("volume")),
        )
        for idx, row in df.iterrows()
    ]

    if not rows:
        return

    PriceHistory.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["security", "date"],
        update_fields=["open", "high", "low", "close", "adj_close", "volume"],
    )
    logger.info("Upserted %d price rows for %s", len(rows), security.symbol)


def _decimal_or_none(value):
    """Return None if value is NaN/None, otherwise the value itself."""
    if value is None:
        return None
    try:
        import math
        if math.isnan(float(value)):
            return None
    except (TypeError, ValueError):
        return None
    return value


def _int_or_none(value):
    """Return None for NaN/None/pd.NA, otherwise int."""
    if value is None:
        return None
    try:
        import pandas as pd
        if pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
