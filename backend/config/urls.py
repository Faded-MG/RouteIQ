from django.urls import include, path

from apps.common.exception_handler import handle_404, handle_500
from apps.common.views import health_live_view, health_ready_view

urlpatterns = [
    path("api/v1/health/live", health_live_view, name="health_live"),
    path("health/live", health_live_view, name="health_live_root"),
    path("api/v1/health/ready", health_ready_view, name="health_ready"),
    path("health/ready", health_ready_view, name="health_ready_root"),
    path("api/v1/", include("apps.planner.urls")),
]

handler404 = handle_404
handler500 = handle_500
