from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditLog

from .message_template_validation import (
    ALLOWED_APPOINTMENT_MESSAGE_PLACEHOLDERS,
    validate_appointment_message_template,
)
from .models import AppointmentMessageTemplate


@transaction.atomic
def save_appointment_message_template(
    *,
    event,
    is_active,
    text_ar,
    text_en,
    actor=None,
):
    """Create/update one event setting with validation and a sanitized audit entry."""
    setting = (
        AppointmentMessageTemplate.objects.select_for_update()
        .filter(event=event)
        .first()
    )
    created = setting is None
    if created:
        setting = AppointmentMessageTemplate(event=event)

    old = {
        "is_active": setting.is_active,
        "text_ar": setting.text_ar,
        "text_en": setting.text_en,
    }
    setting.is_active = bool(is_active)
    setting.text_ar = (text_ar or "").strip()
    setting.text_en = (text_en or "").strip()
    setting.updated_by = (
        actor
        if actor is not None and getattr(actor, "is_authenticated", False)
        else None
    )
    setting.full_clean()
    setting.save()

    changed_fields = [
        field
        for field in ("is_active", "text_ar", "text_en")
        if old[field] != getattr(setting, field)
    ]
    AuditLog.objects.create(
        user=setting.updated_by,
        action=(AuditLog.Action.CREATE if created else AuditLog.Action.SETTINGS_CHANGE),
        app_label="booking",
        model_name="AppointmentMessageTemplate",
        object_id=str(setting.pk),
        object_repr=f"Appointment message {setting.event}",
        message="Appointment message settings updated.",
        metadata={
            "event": setting.event,
            "is_active": setting.is_active,
            "changed_fields": changed_fields,
        },
    )
    return setting


def get_ready_message_template(event, language):
    """Return the active template text, or an empty string when unavailable."""
    language = "en" if language == "en" else "ar"
    setting = AppointmentMessageTemplate.objects.filter(
        event=event,
        is_active=True,
    ).first()
    if setting is None:
        return ""
    return setting.text_en if language == "en" else setting.text_ar


def render_ready_message(appointment, *, event, language, clinic_phone):
    """Render a ready message only; this function never sends or records delivery."""
    template = get_ready_message_template(event, language)
    if not template:
        return ""
    validate_appointment_message_template(template)
    starts_at = timezone.localtime(appointment.starts_at)
    values = {
        "patient_name": appointment.patient.full_name,
        "appointment_date": starts_at.strftime("%Y-%m-%d"),
        "appointment_time": starts_at.strftime("%H:%M"),
        "clinic_phone": clinic_phone,
    }
    try:
        return template.format(**values)
    except (KeyError, ValueError, IndexError) as exc:
        # Stored templates are validated before save. Fail closed if stale or
        # manually-corrupted data bypasses model validation.
        raise ValidationError(
            "Stored appointment message template is invalid."
        ) from exc


__all__ = [
    "ALLOWED_APPOINTMENT_MESSAGE_PLACEHOLDERS",
    "get_ready_message_template",
    "render_ready_message",
    "save_appointment_message_template",
]
