import csv
import base64
from decimal import Decimal
from io import BytesIO
from PIL import Image
import urllib.request

from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.base import ContentFile
from django.conf import settings
from django.template.loader import render_to_string
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
    from django.utils import translation
    
    # Activate Spanish by default if no language is set
    if not translation.get_language():
        translation.activate('es')
    
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

        # ---- 2. Process Signatures ----
        def process_signature(signature_data, filename_prefix):
            """Convert base64 data URL to Django ImageField file."""
            if not signature_data:
                return None
            
            # Remove data URL prefix (e.g., "data:image/png;base64,")
            if ',' in signature_data:
                header, data = signature_data.split(',', 1)
            else:
                data = signature_data
            
            try:
                # Decode base64
                image_data = base64.b64decode(data)
                
                # Create PIL Image
                img = Image.open(BytesIO(image_data))
                
                # Convert to RGB if necessary (for PNG with transparency)
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # Save to BytesIO
                img_io = BytesIO()
                img.save(img_io, format='PNG')
                img_io.seek(0)
                
                # Create Django ContentFile
                filename = f"{filename_prefix}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.png"
                return ContentFile(img_io.read(), name=filename)
            except Exception as e:
                # Log error for debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error processing signature: {e}", exc_info=True)
                # In production, we might want to raise this, but for now return None
                return None

        operator_signature_data = request.POST.get("operator_signature_data")
        administrator_signature_data = request.POST.get("administrator_signature_data")
        administrator_name = (request.POST.get("administrator_name") or "").strip()

        # Debug logging (only in DEBUG mode)
        if settings.DEBUG:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Operator signature data length: {len(operator_signature_data) if operator_signature_data else 0}")
            logger.debug(f"Administrator signature data length: {len(administrator_signature_data) if administrator_signature_data else 0}")

        operator_signature_file = process_signature(operator_signature_data, "operator")
        administrator_signature_file = process_signature(administrator_signature_data, "administrator")

        # ---- 3. Create UsageReport ----
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
            operator_signature=operator_signature_file,
            administrator_name=administrator_name,
            administrator_signature=administrator_signature_file,
        )

        # ---- 4. Create UsagePhotos for uploaded files ----
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

        # ---- 5. Create ChecklistEntries ----
        for item in checklist_items:
            value = request.POST.get(f"check_{item.id}", ChecklistEntry.VALUE_OK)
            comment = (request.POST.get(f"check_comment_{item.id}") or "").strip()
            ChecklistEntry.objects.create(
                usage_report=usage_report,
                item=item,
                value=value,
                comment=comment,
            )

        # ---- 6. Optional: update machine status here (e.g. to IN_USE / AVAILABLE) ----
        # For now we leave it unchanged.

        # ---- 7. Show success page ----
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


@staff_member_required
def report_detail(request, report_id):
    """
    Display complete report details with all photos, checklist, signatures, and map.
    """
    report = get_object_or_404(
        UsageReport.objects.select_related("machine", "job_site").prefetch_related(
            "photos", "checklist_entries__item"
        ),
        pk=report_id,
    )

    # Get all photos grouped by type
    photos = report.photos.all().order_by("photo_type")
    
    # Get checklist entries ordered by display_order
    checklist_entries = report.checklist_entries.all().select_related("item").order_by(
        "item__display_order", "item__label"
    )

    context = {
        "report": report,
        "photos": photos,
        "checklist_entries": checklist_entries,
        "has_location": report.latitude is not None and report.longitude is not None,
    }
    return render(request, "fleet/report_detail.html", context)


@staff_member_required
def report_pdf(request, report_id):
    """
    Generate and download PDF report with all data, images, and map.
    """
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
    except ImportError:
        return HttpResponse(
            "PDF generation requires weasyprint. Please install it: pip install weasyprint",
            status=500,
        )

    report = get_object_or_404(
        UsageReport.objects.select_related("machine", "job_site").prefetch_related(
            "photos", "checklist_entries__item"
        ),
        pk=report_id,
    )

    # Get all photos grouped by type
    photos = report.photos.all().order_by("photo_type")
    
    # Get checklist entries ordered by display_order
    checklist_entries = report.checklist_entries.all().select_related("item").order_by(
        "item__display_order", "item__label"
    )

    # Generate static map image as base64 if location exists
    map_image_base64 = None
    if report.latitude is not None and report.longitude is not None:
        try:
            # Try multiple map services for reliability
            map_services = [
                # OpenStreetMap static map
                f"https://staticmap.openstreetmap.de/staticmap.php?center={report.latitude},{report.longitude}&zoom=15&size=600x400&markers={report.latitude},{report.longitude},red",
                # Alternative: Nominatim-based static map
                f"https://api.mapbox.com/styles/v1/mapbox/streets-v11/static/pin-s+ff0000({report.longitude},{report.latitude})/{report.longitude},{report.latitude},15,0/600x400@2x?access_token=pk.eyJ1IjoibWFwYm94IiwiYSI6ImNpejY4NXVycTA2emYycXBndHRqcmZ3N3gifQ.rJcFIG214AriISLbB6B5aw",
            ]
            
            for map_url in map_services:
                try:
                    req = urllib.request.Request(map_url)
                    req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
                    with urllib.request.urlopen(req, timeout=10) as response:
                        map_image_data = response.read()
                        
                        # Verify it's actually an image
                        if len(map_image_data) > 0:
                            # Process image with PIL to ensure it's in the right format
                            try:
                                img = Image.open(BytesIO(map_image_data))
                                # Convert to RGB if necessary
                                if img.mode in ('RGBA', 'LA', 'P'):
                                    background = Image.new('RGB', img.size, (255, 255, 255))
                                    if img.mode == 'P':
                                        img = img.convert('RGBA')
                                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                                    img = background
                                
                                # Save to BytesIO as PNG
                                img_io = BytesIO()
                                img.save(img_io, format='PNG')
                                img_io.seek(0)
                                map_image_data = img_io.read()
                            except Exception:
                                # If PIL processing fails, use original data
                                pass
                            
                            # Convert to base64 for embedding in PDF
                            map_image_base64 = base64.b64encode(map_image_data).decode('utf-8')
                            break
                except Exception:
                    continue
                    
        except Exception as e:
            # If map download fails, log but don't break PDF generation
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not download map image for PDF: {e}")

    context = {
        "report": report,
        "photos": photos,
        "checklist_entries": checklist_entries,
        "map_image_base64": map_image_base64,
        "has_location": report.latitude is not None and report.longitude is not None,
    }

    # Render HTML template
    html_string = render_to_string("fleet/report_pdf.html", context)

    # Generate PDF
    # Use the request's absolute URI as base_url so weasyprint can resolve relative URLs
    # For S3 images, they should already be absolute URLs, but this helps with any relative paths
    font_config = FontConfiguration()
    base_url = request.build_absolute_uri("/")
    html = HTML(string=html_string, base_url=base_url)
    pdf_file = html.write_pdf(font_config=font_config)

    # Create response
    response = HttpResponse(pdf_file, content_type="application/pdf")
    filename = f"report_{report.machine.code}_{report.date.strftime('%Y%m%d')}_{report.id}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response
