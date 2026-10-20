from django.urls import path

from . import views
from . import optimization_views

urlpatterns = [
    path("api/analyze", views.api_analyze, name="api_analyze"),
    path("analyze", views.analyze_view, name="analyze"),
    path("a/<slug:slug>", views.shared_analysis_view, name="shared_analysis"),
    path("risk", views.risk_view, name="risk"),
    path("optimize", optimization_views.optimize_view, name="optimize"),
    path("api/tickers", views.tickers_autocomplete, name="tickers_autocomplete"),
]
