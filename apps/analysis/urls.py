from django.urls import path

from . import views

urlpatterns = [
    path("analyze", views.analyze_view, name="analyze"),
    path("a/<slug:slug>", views.shared_analysis_view, name="shared_analysis"),
    path("api/tickers", views.tickers_autocomplete, name="tickers_autocomplete"),
]
