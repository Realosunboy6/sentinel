"""Read-only optimization pages, sharing the current analysis selection."""
import logging
import uuid

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .engine import EngineUnavailableError, OptimizationInputError
from .models import Analysis
from .optimization_forms import OptimizationForm, RollingOptimizationForm
from .optimizer import load_optimization_portfolio, optimize_portfolio, rolling_portfolio

logger = logging.getLogger(__name__)


@require_GET
def optimize_view(request):
    return _optimization_page(request)


@require_GET
def risk_parity_view(request):
    return _optimization_page(request, fixed_method="risk_parity")


@require_GET
def rolling_optimization_view(request):
    return _optimization_page(request, rolling=True)


def _optimization_page(request, fixed_method=None, rolling=False):
    title = "Rolling optimization" if rolling else "Risk parity" if fixed_method else "Portfolio optimization"
    slug = request.GET.get("slug", request.session.get("analysis_slug", "")).strip()
    context = {"page_title": title, "rolling": rolling, "fixed_method": fixed_method, "charts": {}}
    template = "analysis/rolling_optimization.html" if rolling else "analysis/optimize.html"
    if not slug:
        return render(request, template, context)
    try:
        analysis, returns, current = load_optimization_portfolio(slug)
        context["analysis"] = analysis
        context["holdings"] = analysis.inputs.get("holdings", [])
        request.session["analysis_slug"] = analysis.slug
        form_class = RollingOptimizationForm if rolling else OptimizationForm
        kwargs = {"symbols": list(current)}
        if fixed_method:
            kwargs["fixed_method"] = fixed_method
        # A bound form with explicit defaults preserves invalid user input and
        # keeps first visits identical to submitting the initial options.
        prototype = form_class(**kwargs)
        options = {name: request.GET.get(name, field.initial if field.initial is not None else "")
                   for name, field in prototype.fields.items()}
        if fixed_method:
            options["method"] = fixed_method
        form = form_class(options, **kwargs)
        context["form"] = form
        if form.is_valid():
            try:
                runner = rolling_portfolio if rolling else optimize_portfolio
                context["report"], context["charts"] = runner(returns, current, **form.engine_options())
            except OptimizationInputError as exc:
                form.add_error(None, str(exc))
        return render(request, template, context)
    except Analysis.DoesNotExist:
        raise Http404("Analysis not found.")
    except OptimizationInputError as exc:
        context["input_error"] = str(exc)
        return render(request, template, context)
    except EngineUnavailableError:
        return render(request, "analysis/engine_unavailable.html", status=503)
    except Exception:
        reference = uuid.uuid4().hex[:10]
        logger.exception("Optimization request failed; reference=%s", reference)
        context["error_reference"] = reference
        return render(request, template, context, status=500)
