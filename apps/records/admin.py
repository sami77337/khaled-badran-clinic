from django import forms
from django.contrib import admin

from .models import ClinicalNote, RecordMedia, VisitRecord


class RecordMediaAdminForm(forms.ModelForm):
    class Meta:
        model = RecordMedia
        fields = "__all__"
        widgets = {
            "file": forms.FileInput(attrs={"aria-label": "Private media file"}),
        }


@admin.register(VisitRecord)
class VisitRecordAdmin(admin.ModelAdmin):
    list_display = (
        "patient",
        "appointment",
        "visit_date",
        "is_visible_to_patient",
        "created_at",
    )
    list_filter = ("is_visible_to_patient", "visit_date", "created_at")
    search_fields = (
        "patient__full_name",
        "patient__phone_raw",
        "patient__phone_e164",
        "visit_reason",
    )
    autocomplete_fields = ("patient", "appointment")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "visit_date"
    list_select_related = ("patient", "appointment")
    fieldsets = (
        (None, {"fields": ("patient", "appointment", "visit_date", "visit_reason")}),
        (
            "Manual Clinical Content",
            {
                "fields": (
                    "doctor_notes",
                    "diagnosis_plan",
                    "instructions",
                    "follow_up_notes",
                )
            },
        ),
        ("Privacy", {"fields": ("is_visible_to_patient",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(ClinicalNote)
class ClinicalNoteAdmin(admin.ModelAdmin):
    list_display = (
        "patient",
        "visit",
        "note_type",
        "is_visible_to_patient",
        "created_by",
        "created_at",
    )
    list_filter = ("note_type", "is_visible_to_patient", "created_at")
    search_fields = (
        "patient__full_name",
        "patient__phone_raw",
        "patient__phone_e164",
        "title",
    )
    autocomplete_fields = ("patient", "visit", "created_by")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
    list_select_related = ("patient", "visit", "created_by")
    fieldsets = (
        (None, {"fields": ("patient", "visit", "note_type", "title", "body", "created_by")}),
        ("Privacy", {"fields": ("is_visible_to_patient",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(RecordMedia)
class RecordMediaAdmin(admin.ModelAdmin):
    form = RecordMediaAdminForm
    list_display = (
        "public_id",
        "patient",
        "visit",
        "media_type",
        "visibility",
        "consent_confirmed",
        "is_active",
        "original_filename",
        "file_size",
        "content_type",
        "uploaded_by",
        "uploaded_at",
    )
    list_filter = (
        "media_type",
        "visibility",
        "consent_confirmed",
        "is_active",
        "uploaded_at",
    )
    search_fields = (
        "patient__full_name",
        "patient__phone_raw",
        "patient__phone_e164",
        "original_filename",
        "title",
    )
    autocomplete_fields = ("patient", "visit", "uploaded_by")
    readonly_fields = (
        "public_id",
        "original_filename",
        "file_size",
        "content_type",
        "private_download_status",
        "uploaded_at",
        "updated_at",
    )
    date_hierarchy = "uploaded_at"
    list_select_related = ("patient", "visit", "uploaded_by")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "patient",
                    "visit",
                    "media_type",
                    "file",
                    "title",
                    "description",
                    "uploaded_by",
                )
            },
        ),
        (
            "Private File Metadata",
            {
                "fields": (
                    "public_id",
                    "original_filename",
                    "file_size",
                    "content_type",
                    "private_download_status",
                )
            },
        ),
        (
            "Privacy And Consent",
            {"fields": ("visibility", "consent_confirmed", "is_active")},
        ),
        ("Timestamps", {"fields": ("uploaded_at", "updated_at")}),
    )

    @admin.display(description="Private download status")
    def private_download_status(self, obj):
        if not obj.pk:
            return "Available after save through the staff-only private route."
        if not obj.is_active:
            return "Inactive media cannot be downloaded."
        if not obj.file:
            return "No private file is stored."
        return "Staff-only private download route; no public file URL is rendered."
