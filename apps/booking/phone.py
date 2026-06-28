import re

from django.core.exceptions import ValidationError


PLUS_NUMBER_RE = re.compile(r"^\+[1-9]\d{7,14}$")
JORDAN_LOCAL_MOBILE_RE = re.compile(r"^07\d{8}$")
JORDAN_INTERNATIONAL_RE = re.compile(r"^\+9627\d{8}$")


def normalize_phone(raw_value):
    value = (raw_value or "").strip()
    if not value:
        raise ValidationError("Phone number is required.")

    compact = re.sub(r"[\s\-().]", "", value)
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    elif compact.startswith("962"):
        compact = "+" + compact

    if JORDAN_LOCAL_MOBILE_RE.match(compact):
        return "+962" + compact[1:]

    if JORDAN_INTERNATIONAL_RE.match(compact):
        return compact

    if compact.startswith("+"):
        if PLUS_NUMBER_RE.match(compact):
            return compact
        raise ValidationError("Enter a plausible international phone number.")

    raise ValidationError("Enter a Jordanian mobile number or an international number starting with +.")
