from django.db import models
from django.core.files.storage import default_storage
import uuid


class Operator(models.Model):
    """Pre-registered machine operators. Selected from dropdown on the usage form."""
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class JobSite(models.Model):
    """Construction job site / project."""

    name = models.CharField(max_length=100, help_text="Project / Job site name")
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Internal code, e.g. SITE-001 or PROJ-MEX-23",
    )
    location = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional address or location description",
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Machine(models.Model):
    """Physical machine (excavator, loader, etc.)."""

    STATUS_AVAILABLE = "AVAILABLE"
    STATUS_IN_USE = "IN_USE"
    STATUS_MAINTENANCE = "MAINTENANCE"
    STATUS_OUT_OF_SERVICE = "OUT_OF_SERVICE"
    STATUS_TRANSIT = "TRANSIT"

    STATUS_CHOICES = [
        (STATUS_AVAILABLE, "Available"),
        (STATUS_IN_USE, "In use"),
        (STATUS_MAINTENANCE, "Under maintenance"),
        (STATUS_OUT_OF_SERVICE, "Out of service"),
        (STATUS_TRANSIT, "In transit"),
    ]

    code = models.CharField(
        max_length=50, unique=True, help_text="Internal ID, e.g. EXC-001"
    )
    name = models.CharField(
        max_length=100, help_text="Human-readable name, e.g. Excavadora CAT 320D"
    )
    type = models.CharField(max_length=50, blank=True, help_text="Excavator, Loader, etc.")
    brand = models.CharField(max_length=50, blank=True)
    model = models.CharField(max_length=50, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)

    qr_slug = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Unique ID used for QR links",
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE
    )

    # Email recipients for report notifications (comma-separated)
    notification_emails = models.TextField(
        blank=True,
        help_text="Comma-separated email addresses to notify when a report is submitted, e.g. manager@macnova.com,supervisor@macnova.com",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def get_notification_emails(self):
        """Return list of notification email addresses."""
        return [e.strip() for e in self.notification_emails.split(",") if e.strip()]


class UsageReport(models.Model):
    """One usage session of a machine."""

    # PROTECT prevents accidental deletion of machines that have reports
    machine = models.ForeignKey(
        Machine,
        on_delete=models.PROTECT,
        related_name="usage_reports",
    )
    operator_name = models.CharField(
        max_length=100, help_text="Name of the operator for this session"
    )

    date = models.DateTimeField(
        db_index=True, help_text="When the operator used the machine"
    )

    # Engine hours — current meter reading at time of report
    engine_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Current hour meter reading at time of report (end reading)",
    )

    # Fuel level (0-100%)
    fuel_level_start = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Fuel level (%) at start"
    )
    fuel_level_end = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Fuel level (%) at end"
    )

    job_site = models.ForeignKey(
        JobSite,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_reports",
        help_text="Project / job site where the machine was used",
    )

    # GPS location where report was submitted
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    notes = models.TextField(blank=True)

    # Signatures stored as PNG images
    operator_signature = models.ImageField(
        upload_to="signatures/", null=True, blank=True
    )
    administrator_name = models.CharField(
        max_length=100, blank=True, help_text="Name of the administrator receiving the machine"
    )
    administrator_signature = models.ImageField(
        upload_to="signatures/", null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.machine.code} - {self.date:%Y-%m-%d} - {self.operator_name}"

    @property
    def hours_used(self):
        """
        Calculate hours used by comparing with the previous report for the same machine.
        Returns None if no previous report exists.
        """
        try:
            previous_report = (
                UsageReport.objects
                .filter(machine=self.machine)
                .filter(
                    models.Q(date__lt=self.date) |
                    (models.Q(date=self.date) & models.Q(created_at__lt=self.created_at))
                )
                .order_by("-date", "-created_at")
                .first()
            )
            if previous_report and previous_report.engine_hours:
                return float(self.engine_hours) - float(previous_report.engine_hours)
            return None
        except (TypeError, ValueError, AttributeError):
            return None


class UsagePhoto(models.Model):
    """Photos attached to a UsageReport."""

    PLACA = "PLACA"
    FRONT = "FRONT"
    BACK = "BACK"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    WHEELS = "WHEELS"
    COCKPIT = "COCKPIT"
    ENGINE = "ENGINE"
    METER = "METER"
    OTHER = "OTHER"

    PHOTO_TYPE_CHOICES = [
        (PLACA, "Placa / Identificación"),
        (FRONT, "Frente"),
        (BACK, "Atrás"),
        (LEFT, "Lado izquierdo"),
        (RIGHT, "Lado derecho"),
        (WHEELS, "Orugas / Neumáticos"),
        (COCKPIT, "Cabina"),
        (ENGINE, "Motor"),
        (METER, "Horómetro"),
        (OTHER, "Otra"),
    ]

    usage_report = models.ForeignKey(
        UsageReport, on_delete=models.CASCADE, related_name="photos"
    )
    photo_type = models.CharField(
        max_length=20, choices=PHOTO_TYPE_CHOICES, default=OTHER
    )
    image = models.ImageField(upload_to="usage_photos/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usage_report} - {self.get_photo_type_display()}"


class ChecklistItem(models.Model):
    """Defines an inspection checklist question, reused across reports."""

    QUESTION_YES_NO = "YES_NO"
    QUESTION_CONDITION = "CONDITION"
    QUESTION_FUEL = "FUEL"
    QUESTION_EXTINTOR = "EXTINTOR"

    QUESTION_TYPE_CHOICES = [
        (QUESTION_YES_NO, "Sí / No"),
        (QUESTION_CONDITION, "Buen estado / Mal estado"),
        (QUESTION_FUEL, "Nivel de combustible (Bajo / Medio / Lleno)"),
        (QUESTION_EXTINTOR, "Extintor (Hay / No hay)"),
    ]

    label = models.CharField(max_length=100, help_text="Short label, e.g. 'Fuga de aceite'")
    description = models.TextField(blank=True, help_text="Optional longer description")
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPE_CHOICES,
        default=QUESTION_YES_NO,
        help_text="Determines which answer options are shown to the operator",
    )
    # Optional: restrict to a machine type. If blank, applies to all.
    machine_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional machine type filter. Leave blank for all.",
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0, help_text="Order in the checklist")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "label"]

    def __str__(self):
        return self.label


class ChecklistEntry(models.Model):
    """Stores the answer to one ChecklistItem for a specific UsageReport."""

    VALUE_CHOICES = [
        # Yes/No questions
        ("SI", "Sí"),
        ("NO", "No"),
        # Condition questions
        ("BUEN_ESTADO", "Buen estado"),
        ("MAL_ESTADO", "Mal estado"),
        # Fuel level
        ("BAJO", "Bajo"),
        ("MEDIO", "Medio"),
        ("LLENO", "Lleno"),
        # Extintor
        ("HAY", "Hay"),
        ("NO_HAY", "No hay"),
        # Legacy values (kept for existing data)
        ("ISSUE", "Hay un problema"),
        ("NO_ISSUE", "Sin problema"),
        ("NA", "N/A"),
    ]

    usage_report = models.ForeignKey(
        UsageReport, on_delete=models.CASCADE, related_name="checklist_entries"
    )
    item = models.ForeignKey(
        ChecklistItem, on_delete=models.CASCADE, related_name="entries"
    )
    value = models.CharField(max_length=20, choices=VALUE_CHOICES)
    comment = models.TextField(blank=True, help_text="Optional notes if there is an issue")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("usage_report", "item")

    def __str__(self):
        return f"{self.usage_report} - {self.item.label} - {self.value}"
