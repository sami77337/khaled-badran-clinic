from django.contrib import admin
from django.db import router, transaction

from .models import AuditLog, DoctorPageContent, PublicReview, SystemSetting
from .review_forms import ReviewModerationForm


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "value_type", "updated_at")
    list_filter = ("value_type",)
    search_fields = ("key", "value", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "user", "model_name", "object_repr")
    list_filter = ("action", "app_label", "model_name", "created_at")
    search_fields = (
        "user__username",
        "app_label",
        "model_name",
        "object_id",
        "object_repr",
        "message",
    )
    readonly_fields = ("created_at",)


@admin.register(DoctorPageContent)
class DoctorPageContentAdmin(admin.ModelAdmin):
    list_display = ("doctor", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Doctor", {"fields": ("doctor",)}),
        ("Hero / professional bio — Arabic", {"fields": ("hero_summary_ar", "credential_label_ar", "professional_bio_ar")}),
        ("Hero / professional bio — English", {"fields": ("hero_summary_en", "credential_label_en", "professional_bio_en")}),
        (
            "Professional path — Arabic",
            {"fields": ("experience_ar", "education_ar", "boards_ar", "memberships_ar", "awards_ar")},
        ),
        (
            "Professional path — English",
            {"fields": ("experience_en", "education_en", "boards_en", "memberships_en", "awards_en")},
        ),
        (
            "Clinical profile — Arabic",
            {"fields": ("languages_ar", "specialties_ar", "conditions_ar")},
        ),
        (
            "Clinical profile — English",
            {"fields": ("languages_en", "specialties_en", "conditions_en")},
        ),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(PublicReview)
class PublicReviewAdmin(admin.ModelAdmin):
    form = ReviewModerationForm

    class Media:
        css = {"all": ("css/admin-review.css",)}

    moderation_fields = (
        "is_approved_for_publication", "is_active", "is_featured", "display_order",
    )
    list_display = (
        "reviewer_name",
        "rating",
        "language",
        "source",
        "is_approved_for_publication",
        "is_active",
        "is_featured",
        "display_order",
        "reviewed_at",
    )
    list_filter = (
        "language",
        "source",
        "rating",
        "is_approved_for_publication",
        "is_active",
        "is_featured",
    )
    search_fields = ("reviewer_name", "body", "source_reference")
    list_editable = (
        "is_approved_for_publication",
        "is_active",
        "is_featured",
        "display_order",
    )
    readonly_fields = (
        "reviewer_name", "body", "rating", "language", "source", "source_reference",
        "submitted_by", "reviewed_at", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def get_changelist_form(self, request, **kwargs):
        kwargs.setdefault("form", self.form)
        return super().get_changelist_form(request, **kwargs)

    def changelist_view(self, request, extra_context=None):
        # Django's change form already has an outer transaction; list editing
        # needs one around validation too, to retain the revision-check locks.
        with transaction.atomic(using=router.db_for_write(self.model)):
            return super().changelist_view(request, extra_context=extra_context)

    def save_model(self, request, obj, form, change):
        # A stale moderation form must never overwrite patient-authored content.
        if change:
            obj.save(update_fields=[*self.moderation_fields, "updated_at"])
