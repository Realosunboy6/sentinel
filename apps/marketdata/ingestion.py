"""Atomic market-data refresh, corporate actions and corrected-price cache expiry."""
from datetime import date
from typing import Optional
import logging
import pandas as pd
from django.db import transaction
from apps.marketdata.models import CorporateAction, PriceHistory, Security
from apps.marketdata.sources import PriceSource, UnknownTickerError

logger = logging.getLogger(__name__)


def ingest_security(symbol: str, source: PriceSource, start: Optional[date] = None) -> Security:
    """Refresh maximum history by default, including retroactive adjustments.

    Fetch before opening a transaction: a failed source leaves no new rows.
    PriceSource returns actions in DataFrame.attrs['actions'].
    """
    symbol = symbol.upper().strip()
    if not source.validate(symbol):
        raise UnknownTickerError(f"Symbol '{symbol}' could not be validated at the data source.")
    df = source.fetch(symbol, start, date.today())
    if df.empty:
        raise UnknownTickerError(f"No price history returned for '{symbol}'.")
    with transaction.atomic():
        security, _ = Security.objects.get_or_create(symbol=symbol, exchange='', defaults={'asset_type': 'stock'})
        # Serialize refreshes for this security. Never hold a DB lock during download.
        security = Security.objects.select_for_update().get(pk=security.pk)
        old = dict(PriceHistory.objects.filter(security=security, date__in=list(df.index)).values_list('date', 'adj_close'))
        revised = any(day in old and old[day] != _decimal_or_none(row['adj_close'])
                      for day, row in df.iterrows())
        _upsert_price_history(security, df)
        for action in df.attrs.get('actions', []):
            CorporateAction.objects.update_or_create(security=security, ex_date=action['ex_date'],
                action_type=action['action_type'], defaults={'ratio': action['ratio']})
        if revised:
            # The locked cache key has no revision field. Expire derived cache,
            # retaining Analysis inputs/slugs so every report can be recomputed.
            from apps.analysis.models import AnalysisResult
            AnalysisResult.objects.all().delete()
            logger.info('Expired result cache after adjusted-history revision: %s', symbol)
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
            close=_decimal_or_none(row["close"]),
            adj_close=_decimal_or_none(row["adj_close"]),
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
    """Return a finite four-decimal SQL price, or None for missing/nonfinite input."""
    if value is None:
        return None
    try:
        import math
        if not math.isfinite(float(value)):
            return None
    except (TypeError, ValueError):
        return None
    from decimal import Decimal, ROUND_HALF_UP
    return Decimal(str(value)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


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
