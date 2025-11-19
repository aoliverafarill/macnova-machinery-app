import csv
from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import (
    F,
    ExpressionWrapper,
    DecimalField,
    Sum,
    Count,
    Max,
)

from .models import (
    Machine,
    JobSite,
    ChecklistItem,
    UsageReport,
    UsagePhoto,
    ChecklistEntry,
)


def machine_usage_view(request, qr_slug):
    """
    Public view: operator scans QR, lands here, fills usage report.
    Creates UsageReport + UsagePhotos + ChecklistEntries on POST.
    """
    machine = get_object_or_404(Machine, qr_slug=qr_slug, is_active=True)

    job_sites = JobSite.objects.filter(is_active=True).order_by("name")
    checklist_items = ChecklistItem.objects.filter(is_active=True).order_by(
        "display_order", "label"
    )

    if request.method == "POST":
        # ---- 1. Basic fields ----
        operator_name = (request.POST.get("operator_name") or "").strip()
        engine_hours_start_raw = request.POST.get("engine_hours_start")
        engine_hours_end_raw = request.POST.get("engine_hours_end")
        fuel_level_start_raw = request.POST.get("fuel_level_start")
        fuel_level_end_raw = request.POST.get("fuel_level_end")
        job_site_id = request.POST.get("job_site")
        notes = (request.POST.get("notes") or "").strip()
        latitude_raw = request.POST.get("latitude")
        longitude_raw = request.POST.get("longitude")

        # Convert to proper types (with basic safety)
        def to_decimal(value):
            if value in (None, "", "None"):
                return None
            try:
                return Decimal(value)
            except Exception:
                return None

        def to_int(value):
            if value in (None, "", "None"):
                return None
            try:
                return int(value)
            except Exception:
                return None

        engine_hours_start = to_decimal(engine_hours_start_raw)
        engine_hours_end = to_decimal(engine_hours_end_raw)
        fuel_level_start = to_int(fuel_level_start_raw)
        fuel_level_end = to_int(fuel_level_end_raw)
        latitude = to_decimal(latitude_raw)
        longitude = to_decimal(longitude_raw)

        job_site = None
        if job_site_id:
            try:
                job_site = JobSite.objects.get(pk=job_site_id, is_active=True)
            except JobSite.DoesNotExist:
                job_site = None

        # ---- 2. Create UsageReport ----
        usage_report = UsageReport.objects.create(
            machine=machine,
            operator_name=operator_name or "Unknown",
            date=timezone.now(),  # later you could pass an explicit datetime
            engine_hours_start=engine_hours_start or Decimal("0"),
            engine_hours_end=engine_hours_end or Decimal("0"),
            fuel_level_start=fuel_level_start,
            fuel_level_end=fuel_level_end,
            job_site=job_site,
            latitude=latitude,
            longitude=longitude,
            notes=notes,
        )

        # ---- 3. Create UsagePhotos for uploaded files ----
        photo_fields = [
            ("photo_front", UsagePhoto.FRONT),
            ("photo_back", UsagePhoto.BACK),
            ("photo_left", UsagePhoto.LEFT),
            ("photo_right", UsagePhoto.RIGHT),
            ("photo_wheels", UsagePhoto.WHEELS),
            ("photo_cockpit", UsagePhoto.COCKPIT),
        ]

        for field_name, photo_type in photo_fields:
            file_obj = request.FILES.get(field_name)
            if file_obj:
                UsagePhoto.objects.create(
                    usage_report=usage_report,
                    photo_type=photo_type,
                    image=file_obj,
                )

        # ---- 4. Create ChecklistEntries ----
        for item in checklist_items:
            value = request.POST.get(f"check_{item.id}", ChecklistEntry.VALUE_OK)
            comment = (request.POST.get(f"check_comment_{item.id}") or "").strip()
            ChecklistEntry.objects.create(
                usage_report=usage_report,
                item=item,
                value=value,
                comment=comment,
            )

        # ---- 5. Optional: update machine status here (e.g. to IN_USE / AVAILABLE) ----
        # For now we leave it unchanged.

        # ---- 6. Show success page ----
        return render(
            request,
            "fleet/machine_usage_success.html",
            {"machine": machine, "usage_report": usage_report},
        )

    # GET: render empty form
    context = {
        "machine": machine,
        "job_sites": job_sites,
        "checklist_items": checklist_items,
    }
    return render(request, "fleet/machine_usage_form.html", context)

@staff_member_required
def manager_dashboard(request):
    """
    Simple dashboard for managers:
    - Filter by date range
    - Show global stats
    - Show per-machine summary
    - Show recent reports
    """
    # ---- Filters ----
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")
    machine_id = request.GET.get("machine")
    job_site_id = request.GET.get("job_site")

    reports = (
        UsageReport.objects
        .select_related("machine", "job_site")
        .prefetch_related("photos")
        .all()
    )

    # Apply date filters (dates in yyyy-mm-dd)
    if date_from_str:
        reports = reports.filter(date__date__gte=date_from_str)
    if date_to_str:
        reports = reports.filter(date__date__lte=date_to_str)

    if machine_id:
        reports = reports.filter(machine_id=machine_id)

    if job_site_id:
        reports = reports.filter(job_site_id=job_site_id)

    # Expression to compute hours_used at DB level
    hours_used_expr = ExpressionWrapper(
        F("engine_hours_end") - F("engine_hours_start"),
        output_field=DecimalField(max_digits=8, decimal_places=2),
    )

    reports = reports.annotate(hours_used_db=hours_used_expr)

    # ---- Global stats ----
    total_reports = reports.count()
    agg = reports.aggregate(total_hours=Sum("hours_used_db"))
    total_hours = agg["total_hours"] or Decimal("0")
    machines_used = (
        reports.values("machine_id").distinct().count() if total_reports > 0 else 0
    )

    # ---- Per-machine summary ----
    per_machine = (
        reports.values(
            "machine_id",
            "machine__code",
            "machine__name",
            "machine__status",
        )
        .annotate(
            total_hours=Sum("hours_used_db"),
            report_count=Count("id"),
            last_usage=Max("date"),
        )
        .order_by("machine__code")
    )

    # ---- Recent reports ----
    recent_reports = reports.order_by("-date")[:25]

    # For filters dropdowns
    machines = Machine.objects.filter(is_active=True).order_by("code")
    job_sites = JobSite.objects.filter(is_active=True).order_by("name")

    context = {
        "total_reports": total_reports,
        "total_hours": total_hours,
        "machines_used": machines_used,
        "per_machine": per_machine,
        "recent_reports": recent_reports,
        "machines": machines,
        "job_sites": job_sites,
        "date_from": date_from_str or "",
        "date_to": date_to_str or "",
        "selected_machine_id": int(machine_id) if machine_id else None,
        "selected_job_site_id": int(job_site_id) if job_site_id else None,
    }
    return render(request, "fleet/manager_dashboard.html", context)

@staff_member_required
def manager_dashboard_export_csv(request):
    """
    Export the same filtered UsageReport queryset as CSV.
    Columns: date, machine, operator, job_site, hours, fuel, GPS.
    """
    # Same filters as manager_dashboard
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")
    machine_id = request.GET.get("machine")
    job_site_id = request.GET.get("job_site")

    reports = UsageReport.objects.select_related("machine", "job_site").all()

    if date_from_str:
        reports = reports.filter(date__date__gte=date_from_str)
    if date_to_str:
        reports = reports.filter(date__date__lte=date_to_str)
    if machine_id:
        reports = reports.filter(machine_id=machine_id)
    if job_site_id:
        reports = reports.filter(job_site_id=job_site_id)

    hours_used_expr = ExpressionWrapper(
        F("engine_hours_end") - F("engine_hours_start"),
        output_field=DecimalField(max_digits=8, decimal_places=2),
    )
    reports = reports.annotate(hours_used_db=hours_used_expr).order_by("date")

    # Build CSV response
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="usage_reports.csv"'
    writer = csv.writer(response)

    # Header
    writer.writerow(
        [
            "report_id",
            "date",
            "machine_code",
            "machine_name",
            "machine_status",
            "operator_name",
            "job_site_code",
            "job_site_name",
            "engine_hours_start",
            "engine_hours_end",
            "hours_used",
            "fuel_level_start",
            "fuel_level_end",
            "latitude",
            "longitude",
        ]
    )

    # Rows
    for r in reports:
        writer.writerow(
            [
                r.id,
                r.date.isoformat(),
                r.machine.code,
                r.machine.name,
                r.machine.status,
                r.operator_name,
                r.job_site.code if r.job_site else "",
                r.job_site.name if r.job_site else "",
                r.engine_hours_start,
                r.engine_hours_end,
                getattr(r, "hours_used_db", None),
                r.fuel_level_start if r.fuel_level_start is not None else "",
                r.fuel_level_end if r.fuel_level_end is not None else "",
                r.latitude if r.latitude is not None else "",
                r.longitude if r.longitude is not None else "",
            ]
        )

    return response
