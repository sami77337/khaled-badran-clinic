from django import forms
from django.contrib import admin
from django.db import transaction

from .storage import schedule_public_case_media_file_deletion

from .models import (
    ClinicalNote,
    PatientTimelineEvent,
    PublicCase,
    PublicCaseMedia,
    RecordMedia,
    RecordMediaFolder,
    VisitRecord,
)


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
        "folder",
        "media_type",
        "visibility",
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
    autocomplete_fields = ("patient", "visit", "folder", "uploaded_by")
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
    list_select_related = ("patient", "visit", "folder", "uploaded_by")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "patient",
                    "visit",
                    "folder",
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
            "Privacy",
            {"fields": ("visibility", "is_active")},
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


@admin.register(PublicCase)
class PublicCaseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "consent_confirmed",
        "is_published",
        "created_by",
        "created_at",
    )
    list_filter = ("consent_confirmed", "is_published", "created_at")
    search_fields = ("title",)
    autocomplete_fields = ("created_by",)
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("created_by",)

    def delete_model(self, request, obj):
        with transaction.atomic():
            media_items = list(obj.media_items.select_for_update())
            schedule_public_case_media_file_deletion(media_items)
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            media_items = list(
                PublicCaseMedia.objects.select_for_update().filter(public_case__in=queryset)
            )
            schedule_public_case_media_file_deletion(media_items)
            super().delete_queryset(request, queryset)


@admin.register(PublicCaseMedia)
class PublicCaseMediaAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "public_case",
        "role",
        "media_type",
        "consent_confirmed",
        "is_active",
        "uploaded_by",
        "uploaded_at",
    )
    list_filter = ("role", "media_type", "consent_confirmed", "is_active", "uploaded_at")
    search_fields = ("public_case__title", "original_filename")
    autocomplete_fields = ("public_case", "uploaded_by")
    readonly_fields = (
        "public_id",
        "original_filename",
        "file_size",
        "content_type",
        "uploaded_at",
        "updated_at",
    )
    list_select_related = ("public_case", "uploaded_by")

    def delete_model(self, request, obj):
        with transaction.atomic():
            schedule_public_case_media_file_deletion([obj])
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            media_items = list(queryset.select_for_update())
            schedule_public_case_media_file_deletion(media_items)
            super().delete_queryset(request, queryset)


@admin.register(PatientTimelineEvent)
class PatientTimelineEventAdmin(admin.ModelAdmin):
    list_display = ("patient", "event_type", "actor", "occurred_at")
    list_filter = ("event_type", "occurred_at")
    search_fields = ("patient__full_name",)
    autocomplete_fields = ("patient", "actor")
    readonly_fields = ("created_at",)
    list_select_related = ("patient", "actor")


@admin.register(RecordMediaFolder)
class RecordMediaFolderAdmin(admin.ModelAdmin):
    list_display = ("name", "patient", "created_by", "created_at", "updated_at")
    search_fields = ("name", "patient__full_name")
    autocomplete_fields = ("patient", "created_by")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("patient", "created_by")
