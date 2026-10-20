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
    from datetime import date
    for security in securities:
        security.stale = not security.latest_date or (date.today() - security.latest_date).days > 10
    return render(request, "core/securities_list.html", {"securities": securities})


def landing_view(request):
    """Only a matching, dated cached K5 analysis supplies the sample card."""
    import json
    from apps.analysis.models import Analysis, AnalysisResult, Preset
    from apps.analysis.charts import build_all_charts
    from apps.analysis.analyzer import canonicalize
    from datetime import date
    k5_metrics = k5_charts_json = None
    preset = Preset.objects.filter(slug='k5-sample').first()
    if preset:
        for analysis in Analysis.objects.order_by('-created_at').iterator():
            inputs = analysis.inputs
            if not inputs.get('holdings') or not inputs.get('start') or not inputs.get('end') or inputs.get('benchmark', 'SPY') != 'SPY':
                continue
            expected = canonicalize(preset.inputs['holdings'], date.fromisoformat(inputs['start']), date.fromisoformat(inputs['end']), 'SPY')
            actual = canonicalize(inputs.get('holdings', []), date.fromisoformat(inputs['start']), date.fromisoformat(inputs['end']), 'SPY')
            if actual != expected:
                continue
            result = AnalysisResult.objects.filter(input_hash=analysis.input_hash).order_by('-data_asof').first()
            if result and result.metrics.get('_input_signature'):
                k5_metrics = result.metrics
                k5_charts_json = json.dumps(build_all_charts(k5_metrics, str(result.data_asof)), allow_nan=False)
                break
    return render(request, 'core/index.html', {'k5_metrics': k5_metrics, 'k5_charts_json': k5_charts_json})
