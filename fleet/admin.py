from django.contrib import admin
from .models import (
    Machine,
    JobSite,
    UsageReport,
    UsagePhoto,
    ChecklistItem,
    ChecklistEntry,
)


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
        "code",
        "name",
        "type",
        "brand",
        "status",
        "qr_slug",      # 👈 visible in admin
        "is_active",
        "created_at",
    )
    readonly_fields = ("qr_slug",)   # 👈 visible but NOT editable
    list_filter = ("type", "brand", "status", "is_active")
    search_fields = ("code", "name", "serial_number")


# -------------------------
#  Usage Photos (inline)
# -------------------------

class UsagePhotoInline(admin.TabularInline):
    model = UsagePhoto
    extra = 0


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
        "machine",
        "operator_name",
        "administrator_name",
        "date",
        "engine_hours_start",
        "engine_hours_end",
        "hours_used",
        "fuel_level_start",
        "fuel_level_end",
        "job_site",
        "created_at",
    )
    list_filter = ("machine", "job_site", "date")
    search_fields = ("machine__code", "operator_name", "administrator_name")
    readonly_fields = ("operator_signature", "administrator_signature")
    inlines = [UsagePhotoInline, ChecklistEntryInline]
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("machine", "operator_name", "date", "job_site")
        }),
        ("Engine Hours", {
            "fields": ("engine_hours_start", "engine_hours_end")
        }),
        ("Fuel Levels", {
            "fields": ("fuel_level_start", "fuel_level_end")
        }),
        ("Location", {
            "fields": ("latitude", "longitude")
        }),
        ("Signatures", {
            "fields": ("operator_signature", "administrator_name", "administrator_signature")
        }),
        ("Notes", {
            "fields": ("notes",)
        }),
    )


# -------------------------
#  Usage Photo
# -------------------------

@admin.register(UsagePhoto)
class UsagePhotoAdmin(admin.ModelAdmin):
    list_display = ("usage_report", "photo_type", "created_at")
    list_filter = ("photo_type",)
    search_fields = ("usage_report__machine__code",)
    
    # Removed debug logging - was only needed for troubleshooting S3 uploads


# -------------------------
#  Checklist Items
# -------------------------

@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("label", "machine_type", "is_active", "display_order")
    list_filter = ("is_active", "machine_type")
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