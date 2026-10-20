"""
Management command: refresh_prices

Usage:
    # Refresh all tracked securities (nightly job):
    python manage.py refresh_prices

    # Seed / refresh specific symbols:
    python manage.py refresh_prices --symbols SPY QQQ BND AAPL MSFT IWM GLD MCK LLY PWR NVDA STX

Failures for individual symbols are logged and reported but do not abort
the rest of the run (yesterday's cache keeps serving per spec §11).
"""

import logging
import sys

from django.core.management.base import BaseCommand

from apps.marketdata.ingestion import ingest_security
from apps.marketdata.models import Security
from apps.marketdata.sources import UnknownTickerError, YahooPriceSource

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Refresh price history for tracked securities (or a given symbol list)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--symbols",
            nargs="+",
            metavar="SYMBOL",
            help=(
                "Space-separated list of ticker symbols to ingest. "
                "If omitted, refreshes every security already in the database."
            ),
        )

    def handle(self, *args, **options):
        source = YahooPriceSource()
        symbols = options.get("symbols") or []

        tracked = Security.objects.order_by("symbol").values_list("symbol", flat=True)
        targets = sorted(set(tracked) | {s.upper().strip() for s in symbols})

        if not targets:
            self.stdout.write(self.style.WARNING("No symbols to refresh."))
            return

        ok = []
        failed = []

        for symbol in targets:
            try:
                security = ingest_security(symbol, source)
                ok.append(symbol)
                self.stdout.write(self.style.SUCCESS(f"  ✓ {symbol}"))
            except UnknownTickerError as exc:
                failed.append((symbol, str(exc)))
                self.stderr.write(self.style.ERROR(f"  ✗ {symbol}: {exc}"))
                logger.error("refresh_prices: unknown ticker %s: %s", symbol, exc)
            except Exception as exc:
                failed.append((symbol, str(exc)))
                self.stderr.write(self.style.ERROR(f"  ✗ {symbol}: {exc}"))
                logger.exception("refresh_prices: unexpected error for %s", symbol)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"Done: {len(ok)} succeeded, {len(failed)} failed.")
        )

        if failed:
            self.stderr.write("\nFailed symbols:")
            for sym, msg in failed:
                self.stderr.write(f"  {sym}: {msg}")
            sys.exit(1)
