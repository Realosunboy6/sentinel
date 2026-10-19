from django.urls import path

from apps.analysis.optimization_views import risk_parity_view, rolling_optimization_view

urlpatterns = [
    path("risk-parity", risk_parity_view, name="risk_parity"),
    path("rolling-optimization", rolling_optimization_view, name="rolling_optimization"),
]
