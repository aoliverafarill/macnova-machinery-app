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
    path(
        "dashboard/report/<int:report_id>/",
        views.report_detail,
        name="report_detail",
    ),
    path(
        "dashboard/report/<int:report_id>/pdf/",
        views.report_pdf,
        name="report_pdf",
    ),
]
