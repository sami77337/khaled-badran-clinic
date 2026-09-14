from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import router, transaction
from django.utils.translation import get_language, gettext_lazy as _

from . import review_moderation
from .models import AuditLog, DoctorPageContent, PublicReview, SystemSetting
from .review_forms import ReviewListModerationForm, ReviewModerationForm


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
    change_form_template = "admin/core/publicreview/change_form.html"

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
    list_editable = moderation_fields
    readonly_fields = (
        "reviewer_name", "body", "rating", "language", "source", "source_reference",
        "submitted_by", "reviewed_at", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    @admin.display(description=_("Status"))
    def publication_status(self, obj):
        visible = obj.is_approved_for_publication and obj.is_active
        if (get_language() or "").startswith("ar"):
            return "ظاهر" if visible else "مخفي"
        return "Visible" if visible else "Hidden"

    def get_fields(self, request, obj=None):
        if obj is not None and review_moderation.is_patient_review(obj):
            fields = (*self.readonly_fields, "publication_status")
            if self.has_change_permission(request, obj):
                fields += ("review_version",)
            return fields
        return super().get_fields(request, obj)

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None and review_moderation.is_patient_review(obj):
            fields += ("publication_status",)
        return fields

    def get_changelist_form(self, request, **kwargs):
        kwargs.setdefault("form", ReviewListModerationForm)
        return super().get_changelist_form(request, **kwargs)

    def changelist_view(self, request, extra_context=None):
        # Imported reviews retain their existing inline editing and row locks.
        with transaction.atomic(using=router.db_for_write(self.model)):
            return super().changelist_view(request, extra_context=extra_context)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context["patient_review"] = obj is not None and review_moderation.is_patient_review(obj)
        context["review_actions_arabic"] = (get_language() or "").startswith("ar")
        return super().render_change_form(request, context, add, change, form_url, obj)

    def save_model(self, request, obj, form, change):
        # A stale moderation form must never overwrite patient-authored content.
        if change:
            if review_moderation.is_patient_review(obj):
                review_moderation.set_patient_review_visibility(obj, form.cleaned_data.get("moderation_action"))
            else:
                obj.save(update_fields=[*self.moderation_fields, "updated_at"])

    def delete_model(self, request, obj):
        # Keep Django's permission/CSRF checks and confirmation page, and require
        # its explicit confirmation value before deleting a patient review.
        if review_moderation.is_patient_review(obj) and (
            request.method != "POST" or request.POST.get("post") != "yes"
        ):
            raise PermissionDenied
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        if request.POST.get("post") != "yes" and review_moderation.patient_reviews(queryset).exists():
            raise PermissionDenied
        super().delete_queryset(request, queryset)
