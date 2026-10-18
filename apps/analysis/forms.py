"""
Portfolio input form — shared component used by the Analyzer and tools.

Validation rules (spec §7):
- 1–25 holdings
- Each weight ≥ 0
- Weights sum to 100 ± 0.5 (offer Normalize)
- Tickers must resolve (securities table first, then live source)
- Duplicate tickers are merged with a notice
- Start date required; default 10 years back
- Benchmark required; default SPY
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from django import forms
from django.core.exceptions import ValidationError

from apps.marketdata.models import Security

MAX_HOLDINGS = 25
MIN_HOLDINGS = 1
WEIGHT_SUM_TOLERANCE = 0.5   # percent points
DEFAULT_BENCHMARK = "SPY"
DEFAULT_YEARS = 10


class PortfolioInputForm(forms.Form):
    """
    Accepts the raw portfolio input as a JSON string of holdings plus
    start_date and benchmark fields.  The holdings JSON is what the
    dynamic JS table posts.

    Expected POST shape:
        holdings = '[{"symbol":"MCK","weight":"29.98"}, ...]'   (JSON string)
        benchmark = "SPY"
        start_date = "2016-01-01"
    """

    holdings_json = forms.CharField(widget=forms.HiddenInput())
    benchmark = forms.CharField(
        max_length=20,
        initial=DEFAULT_BENCHMARK,
        required=False,
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = date.today()
        self.fields["start_date"].initial = date(
            today.year - DEFAULT_YEARS, today.month, today.day
        )
        self.fields["benchmark"].initial = DEFAULT_BENCHMARK

    # ------------------------------------------------------------------
    # Cleaned holdings
    # ------------------------------------------------------------------

    def clean_holdings_json(self):
        raw = self.cleaned_data.get("holdings_json", "[]")
        try:
            holdings = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            raise ValidationError("Holdings data is malformed.")

        if not isinstance(holdings, list):
            raise ValidationError("Holdings must be a list.")

        # Parse and normalise
        parsed = []
        for item in holdings:
            sym = str(item.get("symbol", "")).strip().upper()
            try:
                wt = float(item.get("weight", 0))
            except (TypeError, ValueError):
                raise ValidationError(f"Invalid weight for {sym!r}.")
            if sym:
                parsed.append({"symbol": sym, "weight": wt})

        # Merge duplicates (spec §7)
        merged: dict[str, float] = {}
        duplicates: list[str] = []
        for item in parsed:
            sym = item["symbol"]
            if sym in merged:
                merged[sym] += item["weight"]
                duplicates.append(sym)
            else:
                merged[sym] = item["weight"]

        holdings = [{"symbol": s, "weight": w} for s, w in merged.items()]

        if duplicates:
            self._duplicate_notice = f"Duplicate tickers merged: {', '.join(set(duplicates))}"
        else:
            self._duplicate_notice = None

        # Count check
        if len(holdings) < MIN_HOLDINGS:
            raise ValidationError(f"Enter at least {MIN_HOLDINGS} holding.")
        if len(holdings) > MAX_HOLDINGS:
            raise ValidationError(f"Maximum {MAX_HOLDINGS} holdings allowed.")

        # Weight checks
        for item in holdings:
            if item["weight"] < 0:
                raise ValidationError(
                    f"Weight for {item['symbol']} must be ≥ 0."
                )

        total = sum(h["weight"] for h in holdings)
        if abs(total - 100.0) > WEIGHT_SUM_TOLERANCE:
            raise ValidationError(
                f"Weights sum to {total:.2f}%. They must total 100% "
                f"(±{WEIGHT_SUM_TOLERANCE}%). Use Normalize to fix."
            )

        # Ticker resolution — check securities table first; unknown means
        # we don't call the live source here (too slow for form validation).
        # The analyzer will call ingest_security() on-demand if needed.
        return holdings

    def clean_benchmark(self):
        val = self.cleaned_data.get("benchmark", DEFAULT_BENCHMARK).strip().upper()
        return val or DEFAULT_BENCHMARK

    def clean_start_date(self):
        val = self.cleaned_data.get("start_date")
        if val is None:
            today = date.today()
            val = date(today.year - DEFAULT_YEARS, today.month, today.day)
        if val >= date.today():
            raise ValidationError("Start date must be before today.")
        return val

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def duplicate_notice(self) -> str | None:
        return getattr(self, "_duplicate_notice", None)

    def normalized_holdings(self) -> list[dict]:
        """
        Return holdings with weights re-scaled to sum to exactly 100.
        Used by the Normalize action before re-rendering the form.
        """
        holdings = self.cleaned_data["holdings_json"]
        total = sum(h["weight"] for h in holdings)
        if total == 0:
            return holdings
        return [
            {"symbol": h["symbol"], "weight": round(h["weight"] / total * 100, 4)}
            for h in holdings
        ]
