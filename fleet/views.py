import csv
import base64
import json
import logging
from collections import defaultdict
from decimal import Decimal
from io import BytesIO

from PIL import Image

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Max, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import (
    ChecklistEntry,
    ChecklistItem,
    JobSite,
    Machine,
    Operator,
    UsagePhoto,
    UsageReport,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def process_signature(signature_data, filename_prefix):
    """Convert a base64 data URL to a Django ContentFile (PNG)."""
    if not signature_data:
        logger.warning("Empty signature data for %s", filename_prefix)
        return None

    if "," in signature_data:
        _, data = signature_data.split(",", 1)
    else:
        data = signature_data

    try:
        image_data = base64.b64decode(data)
        if not image_data or len(image_data) < 100:
            logger.warning("Decoded signature too small for %s: %d bytes", filename_prefix, len(image_data) if image_data else 0)
            return None

        img = Image.open(BytesIO(image_data))

        # Flatten transparency to white background for PNG
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background

        img_io = BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)

        filename = f"{filename_prefix}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.png"
        content = img_io.read()
        logger.info("Created signature file %s (%d bytes)", filename, len(content))
        return ContentFile(content, name=filename)

    except Exception as e:
        logger.error("Error processing signature for %s: %s", filename_prefix, e, exc_info=True)
        return None


def process_photo_base64(photo_data, filename_prefix):
    """Convert a base64 data URL (photo) to a Django ContentFile (JPEG)."""
    if not photo_data:
        return None

    if "," in photo_data:
        header, data = photo_data.split(",", 1)
    else:
        header, data = "", photo_data

    try:
        image_data = base64.b64decode(data)
        img = Image.open(BytesIO(image_data))

        # Convert to RGB (JPEG doesn't support alpha)
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Resize if too large (max 1920px on longest side)
        max_size = 1920
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.LANCZOS)

        img_io = BytesIO()
        img.save(img_io, format="JPEG", quality=75)
        img_io.seek(0)

        filename = f"{filename_prefix}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        return ContentFile(img_io.read(), name=filename)

    except Exception as e:
        logger.error("Error processing photo %s: %s", filename_prefix, e, exc_info=True)
        return None


def send_report_notification(usage_report):
    """Send email notification for a usage report. Silently skips if no emails configured."""
    emails = usage_report.machine.get_notification_emails()
    if not emails:
        return

    try:
        html = render_to_string("fleet/email_report.html", {"report": usage_report})
        send_mail(
            subject=f"Reporte: {usage_report.machine.code} — {usage_report.date:%Y-%m-%d}",
            message=f"Reporte de {usage_report.machine.name} por {usage_report.operator_name}.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails,
            html_message=html,
            fail_silently=True,
        )
        logger.info("Sent report notification for report %s to %s", usage_report.id, emails)
    except Exception as e:
        logger.error("Failed to send report notification for %s: %s", usage_report.id, e)


def _build_usage_report(machine, post_data, files_data=None):
    """
    Core logic to create a UsageReport with photos and checklist entries.
    Accepts either request.POST + request.FILES (multipart) or a parsed dict (JSON API).
    Returns the created UsageReport.
    Must be called inside a transaction.atomic() block.
    """
    files_data = files_data or {}

    def to_decimal(value):
        if value in (None, "", "None"):
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def to_int(value):
        if value in (None, "", "None"):
            return None
        try:
            return int(value)
        except Exception:
            return None

    operator_name = (post_data.get("operator_name") or "").strip()
    engine_hours_raw = post_data.get("engine_hours")
    fuel_level_start_raw = post_data.get("fuel_level_start")
    fuel_level_end_raw = post_data.get("fuel_level_end")
    job_site_id = post_data.get("job_site")
    notes = (post_data.get("notes") or "").strip()
    latitude_raw = post_data.get("latitude")
    longitude_raw = post_data.get("longitude")
    administrator_name = (post_data.get("administrator_name") or "").strip()

    engine_hours = to_decimal(engine_hours_raw)
    fuel_level_start = to_int(fuel_level_start_raw)
    fuel_level_end = to_int(fuel_level_end_raw)
    latitude = to_decimal(latitude_raw)
    longitude = to_decimal(longitude_raw)

    job_site = None
    if job_site_id:
        try:
            job_site = JobSite.objects.get(pk=job_site_id, is_active=True)
        except JobSite.DoesNotExist:
            pass

    # Process signatures
    operator_sig_file = process_signature(post_data.get("operator_signature_data"), "operator")
    admin_sig_file = process_signature(post_data.get("administrator_signature_data"), "administrator")

    # Create the report
    usage_report = UsageReport.objects.create(
        machine=machine,
        operator_name=operator_name or "Unknown",
        date=timezone.now(),
        engine_hours=engine_hours or Decimal("0"),
        fuel_level_start=fuel_level_start,
        fuel_level_end=fuel_level_end,
        job_site=job_site,
        latitude=latitude,
        longitude=longitude,
        notes=notes,
        operator_signature=operator_sig_file,
        administrator_name=administrator_name,
        administrator_signature=admin_sig_file,
    )
    logger.info("Created UsageReport %s for machine %s", usage_report.id, machine.code)

    # Photos from multipart file upload
    photo_fields = [
        ("photo_placa", UsagePhoto.PLACA),
        ("photo_front", UsagePhoto.FRONT),
        ("photo_back", UsagePhoto.BACK),
        ("photo_left", UsagePhoto.LEFT),
        ("photo_right", UsagePhoto.RIGHT),
        ("photo_wheels", UsagePhoto.WHEELS),
        ("photo_cockpit", UsagePhoto.COCKPIT),
        ("photo_engine", UsagePhoto.ENGINE),
        ("photo_meter", UsagePhoto.METER),
        ("photo_other", UsagePhoto.OTHER),
    ]
    for field_name, photo_type in photo_fields:
        file_obj = files_data.get(field_name)
        if file_obj:
            UsagePhoto.objects.create(
                usage_report=usage_report, photo_type=photo_type, image=file_obj
            )

    # Photos from base64 (JSON / offline sync)
    photos_base64 = post_data.get("photos_base64") or []
    if isinstance(photos_base64, str):
        try:
            photos_base64 = json.loads(photos_base64)
        except Exception:
            photos_base64 = []

    for photo_entry in photos_base64:
        photo_type = photo_entry.get("type", UsagePhoto.OTHER)
        photo_data = photo_entry.get("data")
        if photo_data:
            file_obj = process_photo_base64(photo_data, f"photo_{photo_type.lower()}")
            if file_obj:
                UsagePhoto.objects.create(
                    usage_report=usage_report, photo_type=photo_type, image=file_obj
                )

    # Checklist entries
    checklist_items = ChecklistItem.objects.filter(is_active=True)
    checklist_data = post_data.get("checklist") or {}

    for item in checklist_items:
        # Support both flat (form POST) and nested (JSON) checklist data
        if isinstance(checklist_data, dict):
            value = checklist_data.get(str(item.id), "")
        else:
            value = post_data.get(f"check_{item.id}", "")

        if not value:
            continue

        comment = ""
        if isinstance(checklist_data, dict):
            comment = (checklist_data.get(f"comment_{item.id}") or "").strip()
        else:
            comment = (post_data.get(f"check_comment_{item.id}") or "").strip()

        ChecklistEntry.objects.create(
            usage_report=usage_report, item=item, value=value, comment=comment
        )

    return usage_report


# ---------------------------------------------------------------------------
# Public operator form (QR code access)
# ---------------------------------------------------------------------------

def machine_usage_view(request, qr_slug):
    """
    Public view: operator scans QR, lands here, fills usage report.
    GET: renders the multi-step form.
    POST: creates UsageReport + photos + checklist entries (multipart fallback).
    """
    machine = get_object_or_404(Machine, qr_slug=qr_slug, is_active=True)

    if request.method == "POST":
        with transaction.atomic():
            usage_report = _build_usage_report(machine, request.POST, request.FILES)

        send_report_notification(usage_report)

        return render(
            request,
            "fleet/machine_usage_success.html",
            {"machine": machine, "usage_report": usage_report},
        )

    # GET — render form
    job_sites = JobSite.objects.filter(is_active=True).order_by("name")
    operators = Operator.objects.filter(is_active=True)
    checklist_items = ChecklistItem.objects.filter(is_active=True)

    # Pre-fill start engine hours from the most recent report for this machine
    last_report = machine.usage_reports.order_by("-date").first()
    last_engine_hours = last_report.engine_hours if last_report else None

    context = {
        "machine": machine,
        "job_sites": job_sites,
        "operators": operators,
        "checklist_items": checklist_items,
        "last_engine_hours": last_engine_hours,
        "yes_no_items": checklist_items.filter(question_type=ChecklistItem.QUESTION_YES_NO),
        "condition_items": checklist_items.filter(question_type=ChecklistItem.QUESTION_CONDITION),
        "fuel_items": checklist_items.filter(question_type=ChecklistItem.QUESTION_FUEL),
        "extintor_items": checklist_items.filter(question_type=ChecklistItem.QUESTION_EXTINTOR),
    }
    return render(request, "fleet/machine_usage_form.html", context)


@csrf_exempt
@require_POST
def machine_usage_submit_api(request, qr_slug):
    """
    JSON API endpoint for offline sync via Service Worker.
    Accepts POST with Content-Type: application/json.
    Photos and signatures are base64-encoded data URLs in the JSON body.
    Returns: {"status": "ok", "report_id": <id>}
    """
    machine = get_object_or_404(Machine, qr_slug=qr_slug, is_active=True)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    try:
        with transaction.atomic():
            usage_report = _build_usage_report(machine, body)
    except Exception as e:
        logger.error("Error creating report via JSON API for machine %s: %s", machine.code, e, exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

    send_report_notification(usage_report)

    return JsonResponse({"status": "ok", "report_id": usage_report.id})


# ---------------------------------------------------------------------------
# Manager dashboard
# ---------------------------------------------------------------------------

@staff_member_required
def manager_dashboard(request):
    """Dashboard for managers: filter, global stats, per-machine summary, recent reports."""

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

    if date_from_str:
        reports = reports.filter(date__date__gte=date_from_str)
    if date_to_str:
        reports = reports.filter(date__date__lte=date_to_str)
    if machine_id:
        reports = reports.filter(machine_id=machine_id)
    if job_site_id:
        reports = reports.filter(job_site_id=job_site_id)

    # Single pass: compute total hours + per-machine stats simultaneously
    total_reports = 0
    total_hours = Decimal("0")
    machine_stats = defaultdict(lambda: {
        "machine_id": None,
        "machine__code": "",
        "machine__name": "",
        "machine__status": "",
        "total_hours": Decimal("0"),
        "report_count": 0,
        "last_usage": None,
    })

    for report in reports:
        total_reports += 1
        hours = report.hours_used
        if hours is not None:
            h = Decimal(str(hours))
            total_hours += h
        else:
            h = None

        mid = report.machine_id
        if machine_stats[mid]["machine_id"] is None:
            machine_stats[mid].update({
                "machine_id": mid,
                "machine__code": report.machine.code,
                "machine__name": report.machine.name,
                "machine__status": report.machine.status,
            })
        machine_stats[mid]["report_count"] += 1
        if h is not None:
            machine_stats[mid]["total_hours"] += h
        if (machine_stats[mid]["last_usage"] is None or
                report.date > machine_stats[mid]["last_usage"]):
            machine_stats[mid]["last_usage"] = report.date

    machines_used = len(machine_stats) if total_reports > 0 else 0
    per_machine = sorted(machine_stats.values(), key=lambda x: x["machine__code"])
    recent_reports = reports.order_by("-date")[:25]

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
    """Export filtered UsageReports as CSV."""

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

    reports = reports.order_by("date")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="usage_reports.csv"'
    writer = csv.writer(response)

    writer.writerow([
        "report_id",
        "date",
        "machine_code",
        "machine_name",
        "machine_status",
        "operator_name",
        "job_site_code",
        "job_site_name",
        "engine_hours",
        "hours_used",
        "fuel_level_start",
        "fuel_level_end",
        "latitude",
        "longitude",
    ])

    for r in reports:
        writer.writerow([
            r.id,
            r.date.isoformat(),
            r.machine.code,
            r.machine.name,
            r.machine.status,
            r.operator_name,
            r.job_site.code if r.job_site else "",
            r.job_site.name if r.job_site else "",
            r.engine_hours,
            r.hours_used if r.hours_used is not None else "",
            r.fuel_level_start if r.fuel_level_start is not None else "",
            r.fuel_level_end if r.fuel_level_end is not None else "",
            r.latitude if r.latitude is not None else "",
            r.longitude if r.longitude is not None else "",
        ])

    return response


@staff_member_required
def report_detail(request, report_id):
    """Display complete report details with photos, checklist, signatures, and map."""
    report = get_object_or_404(
        UsageReport.objects.select_related("machine", "job_site").prefetch_related(
            "photos", "checklist_entries__item"
        ),
        pk=report_id,
    )

    photos = report.photos.all().order_by("photo_type")
    checklist_entries = report.checklist_entries.all().select_related("item").order_by(
        "item__display_order", "item__label"
    )

    map_bbox = None
    if report.latitude is not None and report.longitude is not None:
        lat = float(report.latitude)
        lon = float(report.longitude)
        map_bbox = {
            "min_lon": lon - 0.01,
            "min_lat": lat - 0.01,
            "max_lon": lon + 0.01,
            "max_lat": lat + 0.01,
        }

    context = {
        "report": report,
        "photos": photos,
        "checklist_entries": checklist_entries,
        "has_location": report.latitude is not None and report.longitude is not None,
        "map_bbox": map_bbox,
    }
    return render(request, "fleet/report_detail.html", context)


@staff_member_required
def report_pdf(request, report_id):
    """Generate and download PDF report."""
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
    except ImportError:
        return HttpResponse(
            "PDF generation requires weasyprint. Install it: pip install weasyprint",
            status=500,
        )

    report = get_object_or_404(
        UsageReport.objects.select_related("machine", "job_site").prefetch_related(
            "photos", "checklist_entries__item"
        ),
        pk=report_id,
    )

    photos = report.photos.all().order_by("photo_type")
    checklist_entries = report.checklist_entries.all().select_related("item").order_by(
        "item__display_order", "item__label"
    )

    context = {
        "report": report,
        "photos": photos,
        "checklist_entries": checklist_entries,
        "has_location": report.latitude is not None and report.longitude is not None,
    }

    html_string = render_to_string("fleet/report_pdf.html", context)
    font_config = FontConfiguration()
    base_url = request.build_absolute_uri("/")
    html = HTML(string=html_string, base_url=base_url)
    pdf_file = html.write_pdf(font_config=font_config)

    response = HttpResponse(pdf_file, content_type="application/pdf")
    filename = f"report_{report.machine.code}_{report.date.strftime('%Y%m%d')}_{report.id}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
