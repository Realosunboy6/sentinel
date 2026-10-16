from django.urls import path

from . import views

urlpatterns = [
    path("securities/", views.securities_list, name="securities_list"),
]
