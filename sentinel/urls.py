from django.contrib import admin
from django.urls import path, include

handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("", include("apps.analysis.urls")),
    path("tools/", include("apps.tools.urls")),
]
