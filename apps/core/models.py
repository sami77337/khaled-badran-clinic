from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .content_validation import validate_public_text


class SystemSetting(models.Model):
    class ValueType(models.TextChoices):
        STRING = "string", "String"
        INTEGER = "integer", "Integer"
        BOOLEAN = "boolean", "Boolean"
        DURATION_MINUTES = "duration_minutes", "Duration in minutes"

    APPOINTMENT_REMINDER_OFFSET_MINUTES = "appointment_reminder_offset_minutes"
    BOOKING_ENABLED = "booking_enabled"
    BOOKING_MIN_LEAD_MINUTES = "booking_min_lead_minutes"
    BOOKING_MAX_DAYS_AHEAD = "booking_max_days_ahead"
    BOOKING_SLOT_INTERVAL_MINUTES = "booking_slot_interval_minutes"
    BOOKING_POST_RATE_LIMIT_PER_HOUR = "booking_post_rate_limit_per_hour"
    BOOKING_PHONE_RATE_LIMIT_PER_DAY = "booking_phone_rate_limit_per_day"
    PATIENT_CANCELLATION_CUTOFF_MINUTES = "patient_cancellation_cutoff_minutes"

    key = models.CharField(max_length=100, unique=True)
    value = models.CharField(max_length=255)
    value_type = models.CharField(
        max_length=32,
        choices=ValueType.choices,
        default=ValueType.STRING,
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key

    @classmethod
    def default_appointment_reminder_offset(cls):
        return timedelta(hours=3)


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"
        STATUS_CHANGE = "status_change", "Status change"
        SETTINGS_CHANGE = "settings_change", "Settings change"
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=50, choices=Action.choices)
    app_label = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["app_label", "model_name"]),
        ]

    def __str__(self):
        target = self.object_repr or self.model_name or self.app_label or "system"
        return f"{self.get_action_display()} - {target}"


class DoctorPageContent(models.Model):
    """Owner-editable copy for the public doctor page.

    List-like sections are stored one item per line so the doctor can edit them
    in Django admin without touching JSON or code. Blank fields intentionally
    fall back to the approved source copy in ``apps.core.views``.
    """

    doctor = models.OneToOneField(
        "clinic.Doctor",
        on_delete=models.CASCADE,
        related_name="page_content",
    )
    hero_summary_ar = models.TextField(blank=True)
    hero_summary_en = models.TextField(blank=True)
    credential_label_ar = models.TextField(blank=True)
    credential_label_en = models.TextField(blank=True)
    professional_bio_ar = models.TextField(blank=True)
    professional_bio_en = models.TextField(blank=True)
    experience_ar = models.TextField(blank=True, help_text="One item per line.")
    experience_en = models.TextField(blank=True, help_text="One item per line.")
    education_ar = models.TextField(blank=True, help_text="One item per line.")
    education_en = models.TextField(blank=True, help_text="One item per line.")
    boards_ar = models.TextField(blank=True, help_text="One item per line.")
    boards_en = models.TextField(blank=True, help_text="One item per line.")
    memberships_ar = models.TextField(
        blank=True,
        help_text="One item per line. Use: Label | ACRONYM",
    )
    memberships_en = models.TextField(
        blank=True,
        help_text="One item per line. Use: Label | ACRONYM",
    )
    awards_ar = models.TextField(blank=True, help_text="One item per line.")
    awards_en = models.TextField(blank=True, help_text="One item per line.")
    languages_ar = models.TextField(blank=True, help_text="One item per line.")
    languages_en = models.TextField(blank=True, help_text="One item per line.")
    specialties_ar = models.TextField(blank=True, help_text="One item per line.")
    specialties_en = models.TextField(blank=True, help_text="One item per line.")
    conditions_ar = models.TextField(blank=True, help_text="One item per line.")
    conditions_en = models.TextField(blank=True, help_text="One item per line.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Doctor public page content"
        verbose_name_plural = "Doctor public page content"

    def __str__(self):
        return f"Public page content — {self.doctor}"


class DoctorPageSection(models.Model):
    """Presentation controls; built-in bodies remain in DoctorPageContent."""

    class Presentation(models.TextChoices):
        TEXT = "TEXT", "Text"
        LIST = "LIST", "List"
        CHIPS = "CHIPS", "Chips"
        CARDS = "CARDS", "Cards"

    doctor = models.ForeignKey("clinic.Doctor", on_delete=models.CASCADE, related_name="public_sections")
    # Empty key identifies a custom section. Built-in keys are server controlled.
    key = models.CharField(max_length=32, blank=True)
    title_ar = models.CharField(max_length=180, blank=True, validators=[validate_public_text])
    title_en = models.CharField(max_length=180, blank=True, validators=[validate_public_text])
    content_ar = models.TextField(blank=True, max_length=12000, validators=[validate_public_text])
    content_en = models.TextField(blank=True, max_length=12000, validators=[validate_public_text])
    presentation = models.CharField(max_length=5, choices=Presentation.choices, default=Presentation.LIST)
    display_order = models.PositiveSmallIntegerField(default=90)
    is_visible = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["doctor", "key"], condition=~models.Q(key=""), name="core_unique_builtin_doctor_section"),
        ]


class PublicSiteContent(models.Model):
    """Allowlisted presentation copy, plus visibility of safe Home sections."""

    key = models.CharField(max_length=100, unique=True)
    text_ar = models.TextField(blank=True, max_length=6000, validators=[validate_public_text])
    text_en = models.TextField(blank=True, max_length=6000, validators=[validate_public_text])
    is_visible = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]


class PublicReview(models.Model):
    class Language(models.TextChoices):
        ARABIC = "ar", "Arabic"
        ENGLISH = "en", "English"

    class Source(models.TextChoices):
        GOOGLE = "google", "Google"
        OTHER = "other", "Other approved source"
        PATIENT_PORTAL = "patient_portal", "Patient review"

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_reviews",
    )
    reviewer_name = models.CharField(max_length=160, blank=True)
    body = models.TextField()
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    language = models.CharField(max_length=2, choices=Language.choices, db_index=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.GOOGLE)
    source_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional public source reference only. Do not store secrets or private URLs.",
    )
    is_approved_for_publication = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    display_order = models.PositiveIntegerField(default=0)
    reviewed_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "-reviewed_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["submitted_by"],
                condition=models.Q(source="patient_portal", submitted_by__isnull=False),
                name="core_one_portal_review_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.reviewer_name} ({self.rating}/5)"

    @property
    def star_text(self):
        return "★" * self.rating + "☆" * (5 - self.rating)

    @property
    def public_name_ar(self):
        return self.reviewer_name.strip() or "مريض"

    @property
    def public_name_en(self):
        return self.reviewer_name.strip() or "Patient"
