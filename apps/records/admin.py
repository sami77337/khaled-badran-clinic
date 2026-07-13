from django.contrib import admin

from .models import ClinicalNote, RecordMedia, VisitRecord


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
    list_display = (
        "patient",
        "visit",
        "media_type",
        "visibility",
        "consent_confirmed",
        "is_active",
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
        "title",
    )
    autocomplete_fields = ("patient", "visit")
    readonly_fields = ("uploaded_at", "updated_at")
    date_hierarchy = "uploaded_at"
    list_select_related = ("patient", "visit")
    fieldsets = (
        (None, {"fields": ("patient", "visit", "media_type", "title", "description")}),
        (
            "Privacy And Consent",
            {"fields": ("visibility", "consent_confirmed", "is_active")},
        ),
        ("Timestamps", {"fields": ("uploaded_at", "updated_at")}),
    )
