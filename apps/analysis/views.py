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
            initial_holdings_json = json.dumps(preset_holdings)
            initial_benchmark = preset.inputs.get("settings", {}).get("benchmark", "SPY")
            preset_notice = f"Loaded preset: {preset.name}"
        except Preset.DoesNotExist:
            preset_notice = f"Preset '{preset_slug}' not found."

    if request.method == "GET":
        form = PortfolioInputForm(initial={
            "holdings_json": initial_holdings_json,
            "benchmark": initial_benchmark,
            "start_date": initial_start_date,
        })
        return render(request, "analysis/analyze.html", {
            "form": form,
            "preset_notice": preset_notice,
            "presets": Preset.objects.all(),
        })

    # POST
    action = request.POST.get("action", "analyze")
    form = PortfolioInputForm(request.POST)

    if action == "normalize" and form.is_valid():
        normalized = form.normalized_holdings()
        form = PortfolioInputForm(initial={
            "holdings_json": json.dumps(normalized),
            "benchmark": form.cleaned_data["benchmark"],
            "start_date": form.cleaned_data["start_date"],
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
            benchmark_symbol=benchmark,
        )
    except InvalidTickerError as exc:
        form.add_error("holdings_json", f"Unknown ticker: {exc.symbol}")
        return render(request, "analysis/analyze.html", {
            "form": form,
            "presets": Preset.objects.all(),
        })
    except EngineUnavailableError:
        return render(request, "analysis/engine_unavailable.html", status=503)
    except Exception as exc:
        logger.exception("analyze_view: unexpected error")
        return render(request, "analysis/engine_unavailable.html", {
            "error_detail": str(exc)
        }, status=500)

    # PRG: redirect to share URL
    return redirect("shared_analysis", slug=analysis.slug)


# ---------------------------------------------------------------------------
# Shared analysis (read-only)
# ---------------------------------------------------------------------------

@require_GET
def shared_analysis_view(request, slug):
    analysis = get_object_or_404(Analysis, slug=slug)

    result = (
        AnalysisResult.objects
        .filter(input_hash=analysis.input_hash)
        .order_by("-data_asof")
        .first()
    )
    if result is None:
        raise Http404("Analysis result not found.")

    metrics = result.metrics
    asof = str(result.data_asof)
    charts = build_all_charts(metrics, asof)

    # Build allocation donut from the stored inputs
    stored_holdings = analysis.inputs.get("holdings", [])
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

@require_GET
def risk_view(request):
    """
    GET /risk?slug=<slug>  — full RiskLens report for the given analysis.
    """
    slug = request.GET.get("slug", "").strip()
    if not slug:
        # No slug: prompt the user to run an analysis first.
        return render(request, "analysis/risk_no_analysis.html")

    try:
        from apps.analysis.risklens import get_risklens
        analysis, risk_metrics, charts = get_risklens(slug)
    except Analysis.DoesNotExist:
        raise Http404("Analysis not found.")
    except EngineUnavailableError:
        return render(request, "analysis/engine_unavailable.html", status=503)
    except Exception as exc:
        logger.exception("risk_view: unexpected error for slug=%s", slug)
        return render(request, "analysis/engine_unavailable.html", {
            "error_detail": str(exc)
        }, status=500)

    asof = risk_metrics["data_vintage"]["end"]
    return render(request, "analysis/risk.html", {
        "analysis": analysis,
        "risk": risk_metrics,
        "charts_json": json.dumps(charts),
        "asof": asof,
        "share_url": request.build_absolute_uri(f"/a/{analysis.slug}"),
    })


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
