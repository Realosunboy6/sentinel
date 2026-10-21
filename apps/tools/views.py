import json
import math
from datetime import date

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.analysis.analyzer import make_returns, prepare_prices
from apps.analysis.engine import EngineUnavailableError, OptimizationInputError, run_tool_report
from apps.analysis.errors import engine_error_response
from apps.analysis.forms import PortfolioInputForm
from apps.analysis.models import Analysis

from .catalog import gallery_cards, PARAMETERS, PORTFOLIO_TOOLS, TOOLS


def gallery(request):
    slug = request.GET.get("slug", request.session.get("analysis_slug", ""))
    return render(request, "tools/gallery.html", {"cards": gallery_cards(slug)})


@require_http_methods(["GET", "POST"])
def tool_page(request, code):
    if code not in PORTFOLIO_TOOLS:
        raise Http404("Unknown tool.")
    entry = next(item for item in TOOLS if item[0] == code)
    source = request.POST if request.method == "POST" else request.GET
    slug = source.get("slug", request.session.get("analysis_slug", "")).strip()
    analysis = Analysis.objects.filter(slug=slug).first() if slug else None
    if slug and analysis is None:
        raise Http404("Analysis not found.")
    inputs = analysis.inputs if analysis else {}
    holdings = inputs.get("holdings", [])
    initial = {"holdings_json": json.dumps([
        {"symbol": h["symbol"], "weight": round(float(h["weight"]) * 100, 8)}
        for h in holdings]),
        "benchmark": inputs.get("benchmark", "SPY"),
        "end_date": inputs.get("end", date.today())}
    if inputs.get("start"):
        initial["start_date"] = inputs["start"]
    form = PortfolioInputForm(request.POST if request.method == "POST" else None,
                              initial=initial, cached_only=True)
    params = []
    valid_params = True
    for key, label, kind, default, choices in PARAMETERS.get(code, []):
        raw = source.get(key, default)
        error = ""
        try:
            if kind == "choice":
                if raw not in choices:
                    raise ValueError("Choose a listed option.")
            elif kind == "integer":
                raw = int(raw)
                upper = {"simulations": 10000, "years": 50, "steps": 252,
                         "window": 1000}.get(key, 1000)
                if raw < 1 or raw > upper:
                    raise ValueError("Choose a positive value in the allowed range.")
            else:
                raw = float(raw)
                if not math.isfinite(raw) or not 0 <= raw <= 1e9:
                    raise ValueError("Choose a finite nonnegative value.")
        except (TypeError, ValueError) as exc:
            valid_params = False
            error = str(exc) or "Enter a valid value."
        params.append({"key": key, "label": label, "kind": kind, "value": raw,
                       "choices": choices or [], "error": error})
    context = {"analysis": analysis, "portfolio_form": form,
               "tool": {"code": code, "name": entry[1]}, "params": params}
    if request.method == "POST" and form.is_valid() and valid_params:
        cleaned = form.cleaned_data
        weights = [{"symbol": h["symbol"], "weight": h["weight"] / 100}
                   for h in cleaned["holdings_json"]]
        try:
            effective, prices, warnings = prepare_prices(weights, cleaned["start_date"],
                                                          cleaned["end_date"], cleaned["benchmark"])
            returns = make_returns(prices)
            weights = {h["symbol"]: h["weight"] for h in effective}
            context["report"] = run_tool_report(
                code, returns, prices, weights,
                returns[cleaned["benchmark"]], {p["key"]: p["value"] for p in params})
            context["warnings"] = warnings
        except (ValueError, OptimizationInputError) as exc:
            form.add_error(None, str(exc))
        except EngineUnavailableError:
            return engine_error_response(request, code, status=503)
        except Exception:
            return engine_error_response(request, code, status=500)
    return render(request, "tools/report.html", context)
