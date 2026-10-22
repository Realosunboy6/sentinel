from django.urls import path

from . import views

urlpatterns = [
    path("healthz", views.health_view, name="health"),
    path("", views.landing_view, name="landing"),
    path("securities/", views.securities_list, name="securities_list"),
]
