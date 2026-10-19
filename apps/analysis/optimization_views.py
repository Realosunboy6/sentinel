"""Optimization pages share the Analyzer's editable portfolio component."""
import json
from datetime import date

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .engine import EngineUnavailableError, OptimizationInputError
from .errors import engine_error_response
from .forms import PortfolioInputForm
from .models import Analysis
from .optimization_forms import OptimizationForm, RollingOptimizationForm
from .optimizer import (load_optimization_portfolio, load_optimization_inputs,
                        optimize_portfolio, rolling_portfolio)


@require_http_methods(["GET", "POST"])
def optimize_view(request):
    return _optimization_page(request)


@require_http_methods(["GET", "POST"])
def risk_parity_view(request):
    return _optimization_page(request, fixed_method="risk_parity")


@require_http_methods(["GET", "POST"])
def rolling_optimization_view(request):
    return _optimization_page(request, rolling=True)


def _optimization_page(request, fixed_method=None, rolling=False):
    title = "Rolling optimization" if rolling else "Risk parity" if fixed_method else "Portfolio optimization"
    source = request.POST if request.method == "POST" else request.GET
    slug = source.get("slug", request.session.get("analysis_slug", "")).strip()
    context = {"page_title": title, "rolling": rolling, "fixed_method": fixed_method, "charts": {}}
    template = "analysis/rolling_optimization.html" if rolling else "analysis/optimize.html"
    try:
        analysis = Analysis.objects.get(slug=slug) if slug else None
        holdings = analysis.inputs.get("holdings", []) if analysis else []
        inputs = analysis.inputs if analysis else {}
        context["analysis"] = analysis
        if analysis:
            request.session["analysis_slug"] = analysis.slug
        initial = {"holdings_json": json.dumps([{**h, "weight": round(float(h["weight"]) * 100, 8)} for h in holdings]),
                   "benchmark": inputs.get("benchmark", inputs.get("settings", {}).get("benchmark", "SPY")),
                   "end_date": inputs.get("end", date.today())}
        if inputs.get("start"):
            initial["start_date"] = inputs["start"]
        portfolio_form = PortfolioInputForm(request.POST if request.method == "POST" else None,
                                            initial=initial, cached_only=True)
        context["portfolio_form"] = portfolio_form
        portfolio_valid = portfolio_form.is_valid() if request.method == "POST" else bool(analysis)
        if request.method == "POST" and portfolio_valid:
            holdings = [{"symbol": h["symbol"], "weight": h["weight"] / 100}
                        for h in portfolio_form.cleaned_data["holdings_json"]]
        form_class = RollingOptimizationForm if rolling else OptimizationForm
        kwargs = {"symbols": [h["symbol"] for h in holdings]}
        if fixed_method:
            kwargs["fixed_method"] = fixed_method
        prototype = form_class(**kwargs)
        options = {name: source.get(name, field.initial if field.initial is not None else "")
                   for name, field in prototype.fields.items()}
        if fixed_method:
            options["method"] = fixed_method
        form = form_class(options, **kwargs)
        context["form"] = form
        if form.is_valid() and portfolio_valid:
            try:
                if request.method == "POST":
                    data = portfolio_form.cleaned_data
                    returns, current = load_optimization_inputs(holdings, data["start_date"], data["end_date"])
                else:
                    _, returns, current = load_optimization_portfolio(slug)
                runner = rolling_portfolio if rolling else optimize_portfolio
                context["report"], context["charts"] = runner(returns, current, **form.engine_options())
            except OptimizationInputError as exc:
                form.add_error(None, str(exc))
        return render(request, template, context)
    except Analysis.DoesNotExist:
        raise Http404("Analysis not found.")
    except EngineUnavailableError:
        return engine_error_response(request, "optimization", status=503)
    except Exception:
        return engine_error_response(request, "optimization", status=500)
