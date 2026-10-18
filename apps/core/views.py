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


def landing_view(request):
    """
    Landing page.

    Hero chart: use the cached K5 result if available (cold-start fallback:
    render the design package's static SVG growth chart — never a 500, never
    fabricated data).
    """
    from apps.analysis.models import Analysis, AnalysisResult
    from apps.analysis.models import Preset

    k5_charts_json = None
    k5_metrics = None

    try:
        k5_preset = Preset.objects.filter(slug="k5-sample").first()
        if k5_preset:
            # Find the most recent cached result for any analysis matching k5
            # holdings (by looking for a recent AnalysisResult — best-effort).
            latest_result = AnalysisResult.objects.order_by("-data_asof").first()
            if latest_result:
                import json
                from apps.analysis.charts import build_all_charts
                k5_metrics = latest_result.metrics
                k5_charts_json = json.dumps(
                    build_all_charts(k5_metrics, str(latest_result.data_asof))
                )
    except Exception:
        pass  # cold start — fallback to static SVG in the template

    return render(request, "core/index.html", {
        "k5_charts_json": k5_charts_json,
        "k5_metrics": k5_metrics,
    })
