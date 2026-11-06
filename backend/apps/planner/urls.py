from django.urls import path

from apps.planner.views import PlanView

app_name = "planner"

urlpatterns = [
    path("routes/plan", PlanView.as_view(), name="plan_route"),
]
