from django.shortcuts import render
from django.db.models import Count, Max

from apps.marketdata.models import Security


def securities_list(request):
    """
    M0 gate page: list every tracked security with its price count and
    latest price date.
    """
    securities = (
        Security.objects.annotate(
            price_count=Count("pricehistory"),
            latest_date=Max("pricehistory__date"),
        )
        .order_by("symbol")
    )
    return render(request, "core/securities_list.html", {"securities": securities})
