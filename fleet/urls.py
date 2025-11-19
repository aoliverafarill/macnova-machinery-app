from django.urls import path
from . import views

app_name = "fleet"

urlpatterns = [
    path(
        "m/<uuid:qr_slug>/",
        views.machine_usage_view,
        name="machine_usage",
    ),
    path(
        "dashboard/",
        views.manager_dashboard,
        name="manager_dashboard",
    ),
    path(
        "dashboard/export/",
        views.manager_dashboard_export_csv,
        name="manager_dashboard_export_csv",
    ),
]
