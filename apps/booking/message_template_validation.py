import re

from django.core.exceptions import ValidationError


ALLOWED_APPOINTMENT_MESSAGE_PLACEHOLDERS = (
    "patient_name",
    "appointment_date",
    "appointment_time",
    "clinic_phone",
)
_ALLOWED_PLACEHOLDER_PATTERN = re.compile(
    r"\{(?:" + "|".join(ALLOWED_APPOINTMENT_MESSAGE_PLACEHOLDERS) + r")\}"
)


def validate_appointment_message_template(value):
    """Allow plain text plus a small, explicit placeholder vocabulary."""
    if not value:
        return
    remainder = _ALLOWED_PLACEHOLDER_PATTERN.sub("", value)
    if "{" in remainder or "}" in remainder:
        raise ValidationError(
            "Unsupported appointment message placeholder or formatting syntax."
        )
