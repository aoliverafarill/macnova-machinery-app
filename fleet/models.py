from django.db import models
from django.conf import settings
import uuid

# Function to get storage at runtime (called when field is accessed)
def get_storage():
    from django.core.files.storage import default_storage
    return default_storage


class JobSite(models.Model):
    """
    Construction job site / project.
    Used as a dropdown in UsageReport.
    """

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
    """
    Physical machine (excavator, loader, etc.).
    """

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
        max_length=50,
        unique=True,
        help_text="Internal ID, e.g. EXC-001",
    )
    name = models.CharField(
        max_length=100,
        help_text="Human-readable name, e.g. Excavadora CAT 320D",
    )
    type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Excavator, Loader, etc.",
    )
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
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_AVAILABLE,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class UsageReport(models.Model):
    """
    One usage session of a machine (like a rental session).
    """

    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="usage_reports",
    )
    operator_name = models.CharField(
        max_length=100,
        help_text="Name of the operator for this session",
    )

    date = models.DateTimeField(
        help_text="When the operator used the machine",
    )

    # Engine hours
    engine_hours_start = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Hour meter before use",
    )
    engine_hours_end = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Hour meter after use",
    )

    # Fuel level (0-100%)
    fuel_level_start = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Fuel level (%) at start",
    )
    fuel_level_end = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Fuel level (%) at end",
    )

    # Job site / project (dropdown)
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
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Latitude of the machine when report was created",
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Longitude of the machine when report was created",
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.machine.code} - {self.date:%Y-%m-%d} - {self.operator_name}"

    @property
    def hours_used(self):
        try:
            return float(self.engine_hours_end) - float(self.engine_hours_start)
        except (TypeError, ValueError):
            return None


class UsagePhoto(models.Model):
    """
    Photos attached to a UsageReport (front, back, sides, etc.).
    """

    FRONT = "FRONT"
    BACK = "BACK"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    WHEELS = "WHEELS"
    COCKPIT = "COCKPIT"
    OTHER = "OTHER"

    PHOTO_TYPE_CHOICES = [
        (FRONT, "Front"),
        (BACK, "Back"),
        (LEFT, "Left side"),
        (RIGHT, "Right side"),
        (WHEELS, "Wheels / Tracks"),
        (COCKPIT, "Cockpit / Controls"),
        (OTHER, "Other"),
    ]

    usage_report = models.ForeignKey(
        UsageReport,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    photo_type = models.CharField(
        max_length=20,
        choices=PHOTO_TYPE_CHOICES,
        default=OTHER,
    )
    image = models.ImageField(
        upload_to="usage_photos/",
        storage=get_storage  # Pass callable - Django will call it at runtime
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usage_report} - {self.get_photo_type_display()}"


class ChecklistItem(models.Model):
    """
    Defines an inspection checklist question, reused across reports.
    Example: 'Check tires', 'Check for visible leaks', etc.
    """

    label = models.CharField(
        max_length=100,
        help_text="Short label, e.g. 'Check tires'",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional longer description / instructions",
    )
    # Optional: restrict to a machine type. If blank, applies to all.
    machine_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional machine type filter, e.g. 'Excavator'. Leave blank for all.",
    )

    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Ordering in the checklist",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "label"]

    def __str__(self):
        return self.label


class ChecklistEntry(models.Model):
    """
    Stores the answer to one ChecklistItem for a specific UsageReport.
    """

    VALUE_OK = "OK"
    VALUE_ISSUE = "ISSUE"
    VALUE_NA = "NA"

    VALUE_CHOICES = [
        (VALUE_OK, "OK"),
        (VALUE_ISSUE, "Issue"),
        (VALUE_NA, "Not applicable"),
    ]

    usage_report = models.ForeignKey(
        UsageReport,
        on_delete=models.CASCADE,
        related_name="checklist_entries",
    )
    item = models.ForeignKey(
        ChecklistItem,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    value = models.CharField(
        max_length=10,
        choices=VALUE_CHOICES,
        default=VALUE_OK,
    )
    comment = models.TextField(
        blank=True,
        help_text="Optional notes if there is an issue",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("usage_report", "item")

    def __str__(self):
        return f"{self.usage_report} - {self.item.label} - {self.value}"
