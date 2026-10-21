from django.urls import path

from apps.analysis.optimization_views import risk_parity_view, rolling_optimization_view
from .views import gallery, tool_page

urlpatterns = [
    path("", gallery, name="tool_gallery"),
    path("risk-parity", risk_parity_view, name="risk_parity"),
    path("rolling-optimization", rolling_optimization_view, name="rolling_optimization"),
    path("<slug:code>", tool_page, name="tool_page"),
]
