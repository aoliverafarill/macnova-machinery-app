from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Operator,
    Machine,
    JobSite,
    UsageReport,
    UsagePhoto,
    ChecklistItem,
    ChecklistEntry,
)


# -------------------------
#  Operator
# -------------------------

@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


# -------------------------
#  Job Site
# -------------------------

@admin.register(JobSite)
class JobSiteAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "location")


# -------------------------
#  Machine
# -------------------------

@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = (
        "code", "name", "type", "brand", "status", "qr_slug", "is_active", "created_at",
    )
    readonly_fields = ("qr_slug",)
    list_filter = ("type", "brand", "status", "is_active")
    search_fields = ("code", "name", "serial_number")
    fieldsets = (
        ("Basic Information", {
            "fields": ("code", "name", "type", "brand", "model", "serial_number", "year", "status", "is_active")
        }),
        ("QR Code", {
            "fields": ("qr_slug",),
            "description": "Unique identifier used in QR codes. Not editable.",
        }),
        ("Email Notifications", {
            "fields": ("notification_emails",),
            "description": "Comma-separated email addresses that receive a notification when a report is submitted for this machine. Leave blank to disable notifications.",
        }),
    )


# -------------------------
#  Usage Photos (inline)
# -------------------------

class UsagePhotoInline(admin.TabularInline):
    model = UsagePhoto
    extra = 0
    readonly_fields = ("photo_preview",)

    def photo_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-width:150px;max-height:100px;" />', obj.image.url)
        return "—"
    photo_preview.short_description = "Preview"


# -------------------------
#  Checklist Entries (inline)
# -------------------------

class ChecklistEntryInline(admin.TabularInline):
    model = ChecklistEntry
    extra = 0


# -------------------------
#  Usage Report
# -------------------------

@admin.register(UsageReport)
class UsageReportAdmin(admin.ModelAdmin):
    list_display = (
        "machine", "operator_name", "administrator_name", "date",
        "engine_hours", "hours_used", "fuel_level_start", "fuel_level_end",
        "job_site", "has_signatures", "created_at",
    )
    list_filter = ("machine", "job_site", "date")
    search_fields = ("machine__code", "operator_name", "administrator_name")
    inlines = [UsagePhotoInline, ChecklistEntryInline]

    fieldsets = (
        ("Basic Information", {
            "fields": ("machine", "operator_name", "date", "job_site")
        }),
        ("Engine Hours", {
            "fields": ("engine_hours",)
        }),
        ("Fuel Levels", {
            "fields": ("fuel_level_start", "fuel_level_end")
        }),
        ("Location", {
            "fields": ("latitude", "longitude")
        }),
        ("Signatures", {
            "fields": ("operator_signature", "administrator_name", "administrator_signature"),
            "description": "Both operator and administrator signatures are required.",
        }),
        ("Notes", {
            "fields": ("notes",)
        }),
    )

    def has_signatures(self, obj):
        has_op = bool(obj.operator_signature)
        has_admin = bool(obj.administrator_signature)
        if has_op and has_admin:
            return "✓ Ambas"
        elif has_op or has_admin:
            return "⚠ Parcial"
        return "✗ Ninguna"
    has_signatures.short_description = "Firmas"


# -------------------------
#  Usage Photo
# -------------------------

@admin.register(UsagePhoto)
class UsagePhotoAdmin(admin.ModelAdmin):
    list_display = ("usage_report", "photo_type", "created_at")
    list_filter = ("photo_type",)
    search_fields = ("usage_report__machine__code",)


# -------------------------
#  Checklist Items
# -------------------------

@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("label", "question_type", "machine_type", "is_active", "display_order")
    list_filter = ("is_active", "question_type", "machine_type")
    search_fields = ("label", "description")
    ordering = ("display_order",)


# -------------------------
#  Checklist Entry
# -------------------------

@admin.register(ChecklistEntry)
class ChecklistEntryAdmin(admin.ModelAdmin):
    list_display = ("usage_report", "item", "value", "comment", "created_at")
    list_filter = ("value", "item")
    search_fields = ("usage_report__machine__code", "item__label")
