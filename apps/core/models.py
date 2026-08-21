from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


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


class PublicReview(models.Model):
    class Language(models.TextChoices):
        ARABIC = "ar", "Arabic"
        ENGLISH = "en", "English"

    class Source(models.TextChoices):
        GOOGLE = "google", "Google"
        OTHER = "other", "Other approved source"

    reviewer_name = models.CharField(max_length=160)
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

    def __str__(self):
        return f"{self.reviewer_name} ({self.rating}/5)"

    @property
    def star_text(self):
        return "★" * self.rating + "☆" * (5 - self.rating)
