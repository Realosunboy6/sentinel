"""
Analysis views:
  - analyze_view         GET/POST  /analyze
  - shared_analysis      GET       /a/<slug>
  - risk_view            GET       /risk?slug=<slug>
  - tickers_autocomplete GET       /api/tickers?q=
"""

from __future__ import annotations

import json
import logging
from datetime import date

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.analysis.analyzer import InvalidTickerError, analyze
from apps.analysis.charts import build_all_charts, allocation_donut_chart
from apps.analysis.engine import EngineUnavailableError
from apps.analysis.errors import engine_error_response
from apps.analysis.forms import PortfolioInputForm
from apps.analysis.models import Analysis, AnalysisResult, Preset
from apps.marketdata.models import Security

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Analyzer — GET (form) / POST (run analysis)
# ---------------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
def analyze_view(request):
    preset_notice = None
    duplicate_notice = None
    initial_holdings_json = "[]"
    initial_benchmark = "SPY"
    initial_start_date = None

    # Pre-fill from preset query param
    preset_slug = request.GET.get("preset")
    if preset_slug:
        try:
            preset = Preset.objects.get(slug=preset_slug)
            preset_holdings = preset.inputs.get("holdings", [])
            initial_holdings_json = json.dumps([{**h, "weight": round(float(h["weight"]) * 100, 8)} for h in preset_holdings])
            initial_benchmark = preset.inputs.get("settings", {}).get("benchmark", "SPY")
            preset_notice = f"Loaded preset: {preset.name}"
        except Preset.DoesNotExist:
            preset_notice = f"Preset '{preset_slug}' not found."

    if request.method == "GET":
        form = PortfolioInputForm(initial={
            "holdings_json": initial_holdings_json,
            "benchmark": initial_benchmark,
        })
        return render(request, "analysis/analyze.html", {
            "form": form,
            "preset_notice": preset_notice,
            "presets": Preset.objects.all(),
        })

    # POST
    action = request.POST.get("action", "analyze")
    form = PortfolioInputForm(request.POST, normalize=action == "normalize")

    if action == "normalize" and form.is_valid():
        normalized = form.normalized_holdings()
        form = PortfolioInputForm(initial={
            "holdings_json": json.dumps(normalized),
            "benchmark": form.cleaned_data["benchmark"],
            "start_date": form.cleaned_data["start_date"],
            "end_date": form.cleaned_data["end_date"],
        })
        return render(request, "analysis/analyze.html", {
            "form": form,
            "normalize_notice": "Weights normalized to 100%.",
            "presets": Preset.objects.all(),
        })

    if not form.is_valid():
        return render(request, "analysis/analyze.html", {
            "form": form,
            "presets": Preset.objects.all(),
        })

    holdings = form.cleaned_data["holdings_json"]
    benchmark = form.cleaned_data["benchmark"]
    start_date = form.cleaned_data["start_date"]

    # Convert percent weights (0–100) → fraction (0–1) for the engine
    holdings_frac = [
        {"symbol": h["symbol"], "weight": h["weight"] / 100.0}
        for h in holdings
    ]

    try:
        analysis, _metrics = analyze(
            holdings=holdings_frac,
            start_date=start_date,
            end_date=form.cleaned_data["end_date"],
            benchmark_symbol=benchmark,
        )
    except InvalidTickerError as exc:
        form.add_error("holdings_json", f"No cached ticker: {exc.symbol}. Add its history with the price refresh job.")
        return render(request, "analysis/analyze.html", {
            "form": form,
            "presets": Preset.objects.all(),
        })
    except ValueError as exc:
        form.add_error(None, str(exc))
        return render(request, "analysis/analyze.html", {"form": form, "presets": Preset.objects.all()})
    except EngineUnavailableError:
        return engine_error_response(request, "analyze", status=503)
    except Exception as exc:
        return engine_error_response(request, "analyze", status=500)

    # PRG: redirect to share URL
    return redirect("shared_analysis", slug=analysis.slug)


# ---------------------------------------------------------------------------
# Shared analysis (read-only)
# ---------------------------------------------------------------------------

@require_GET
def shared_analysis_view(request, slug):
    analysis = get_object_or_404(Analysis, slug=slug)
    request.session["analysis_slug"] = analysis.slug

    result = AnalysisResult.objects.filter(input_hash=analysis.input_hash).order_by('-data_asof').first()
    try:
        inputs = analysis.inputs
        if inputs.get('start') and inputs.get('end'):
            _, metrics = analyze(inputs['holdings'], date.fromisoformat(inputs['start']),
                date.fromisoformat(inputs['end']), inputs.get('benchmark', 'SPY'))
            asof = metrics['data_vintage']['end'][:10]
        elif result is not None:
            metrics, asof = result.metrics, str(result.data_asof)
        else:
            raise Http404('Analysis result not found.')
    except (ValueError, InvalidTickerError, EngineUnavailableError):
        return engine_error_response(request, 'shared-analysis', status=503)
    charts = build_all_charts(metrics, asof)

    # Build allocation donut from the stored inputs
    stored_holdings = metrics.get("effective_holdings", analysis.inputs.get("holdings", []))
    symbols = [h["symbol"] for h in stored_holdings]
    weights = [h["weight"] for h in stored_holdings]
    charts["allocation"] = allocation_donut_chart(symbols, weights, asof)

    return render(request, "analysis/shared.html", {
        "analysis": analysis,
        "metrics": metrics,
        "charts_json": json.dumps(charts),
        "asof": asof,
        "share_url": request.build_absolute_uri(),
        "data_vintage": metrics.get("data_vintage", {}),
    })


# ---------------------------------------------------------------------------
# RiskLens
# ---------------------------------------------------------------------------

@require_http_methods(['GET', 'POST'])
def risk_view(request):
    source = request.POST if request.method == 'POST' else request.GET
    slug = source.get('slug', request.session.get('analysis_slug', '')).strip()
    analysis = get_object_or_404(Analysis, slug=slug) if slug else None
    inputs = analysis.inputs if analysis else {}
    initial = {'holdings_json': json.dumps([{**h, 'weight': round(h['weight'] * 100, 8)} for h in inputs.get('holdings', [])]),
               'benchmark': inputs.get('benchmark', 'SPY')}
    for field, key in [('start_date', 'start'), ('end_date', 'end')]:
        if inputs.get(key):
            initial[field] = inputs[key]
    form = PortfolioInputForm(request.POST if request.method == 'POST' else None, initial=initial, cached_only=True)
    context = {'portfolio_form': form, 'analysis': analysis}
    try:
        if request.method == 'POST':
            if not form.is_valid():
                return render(request, 'analysis/risk_no_analysis.html', context)
            data = form.cleaned_data
            holdings = [{**h, 'weight': h['weight'] / 100} for h in data['holdings_json']]
            analysis, _ = analyze(holdings, data['start_date'], data['end_date'], data['benchmark'])
            request.session['analysis_slug'] = analysis.slug
            return redirect('/risk?slug=' + analysis.slug)
        if analysis is None:
            return render(request, 'analysis/risk_no_analysis.html', context)
        from apps.analysis.risklens import get_risklens
        analysis, risk_metrics, charts = get_risklens(analysis.slug)
    except Analysis.DoesNotExist:
        raise Http404('Analysis not found.')
    except (ValueError, InvalidTickerError) as exc:
        form.add_error(None, str(exc))
        return render(request, 'analysis/risk_no_analysis.html', context)
    except EngineUnavailableError:
        return engine_error_response(request, 'risk', status=503)
    except Exception:
        return engine_error_response(request, 'risk', status=500)
    request.session['analysis_slug'] = analysis.slug
    return render(request, 'analysis/risk.html', {**context, 'analysis': analysis, 'risk': risk_metrics,
        'charts_json': json.dumps(charts, allow_nan=False), 'asof': risk_metrics['data_vintage']['end'],
        'share_url': request.build_absolute_uri(f'/a/{analysis.slug}')})


@require_http_methods(['POST'])
def api_analyze(request):
    try:
        payload = json.loads(request.body) if request.content_type == 'application/json' else request.POST.dict()
        if not isinstance(payload, dict):
            raise ValueError('Analysis input must be a JSON object.')
        if 'holdings' in payload:
            payload['holdings_json'] = json.dumps(payload['holdings'])
        form = PortfolioInputForm(payload, cached_only=True)
        if not form.is_valid():
            return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
        data = form.cleaned_data
        holdings = [{**h, 'weight': h['weight'] / 100} for h in data['holdings_json']]
        analysis, metrics = analyze(holdings, data['start_date'], data['end_date'], data['benchmark'])
        asof = metrics['data_vintage']['end'][:10]
        charts = build_all_charts(metrics, asof)
        effective = metrics.get('effective_holdings', holdings)
        charts['allocation'] = allocation_donut_chart([h['symbol'] for h in effective], [h['weight'] for h in effective], asof)
        request.session['analysis_slug'] = analysis.slug
        return JsonResponse({'slug': analysis.slug, 'share_url': f'/a/{analysis.slug}', 'metrics': metrics, 'charts': charts}, json_dumps_params={'allow_nan': False})
    except (ValueError, InvalidTickerError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except Exception:
        import uuid
        reference = uuid.uuid4().hex[:12]
        logger.exception('API analysis failed reference=%s', reference)
        return JsonResponse({'error': 'Analysis unavailable.', 'reference': reference}, status=503)


# ---------------------------------------------------------------------------
# Ticker autocomplete
# ---------------------------------------------------------------------------

@require_GET
def tickers_autocomplete(request):
    q = request.GET.get("q", "").strip().upper()
    if not q or len(q) < 1:
        return JsonResponse([], safe=False)

    qs = (
        Security.objects
        .filter(symbol__istartswith=q)
        .order_by("symbol")
        .values("symbol", "name", "asset_type")[:15]
    )
    results = [
        {"symbol": s["symbol"], "name": s["name"] or "", "asset_type": s["asset_type"]}
        for s in qs
    ]
    return JsonResponse(results, safe=False)
