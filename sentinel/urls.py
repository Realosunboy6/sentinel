from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("", include("apps.analysis.urls")),
    path("tools/", include("apps.tools.urls")),
]
