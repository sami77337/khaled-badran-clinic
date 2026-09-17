from string import Formatter

from django.core.exceptions import ValidationError


ALLOWED_APPOINTMENT_MESSAGE_PLACEHOLDERS = (
    "patient_name",
    "appointment_date",
    "appointment_time",
    "clinic_phone",
)
_ALLOWED_PLACEHOLDER_SET = frozenset(ALLOWED_APPOINTMENT_MESSAGE_PLACEHOLDERS)


def validate_appointment_message_template(value):
    """Allow plain text plus a small, explicit placeholder vocabulary."""
    if not value:
        return
    try:
        parts = Formatter().parse(value)
        for _literal, field_name, format_spec, conversion in parts:
            if field_name is None:
                continue
            if (
                field_name not in _ALLOWED_PLACEHOLDER_SET
                or format_spec
                or conversion
            ):
                raise ValidationError(
                    "Unsupported appointment message placeholder or formatting syntax."
                )
    except (ValueError, IndexError) as exc:
        raise ValidationError("Invalid appointment message template syntax.") from exc
