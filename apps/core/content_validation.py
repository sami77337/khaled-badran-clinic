"""Plain public copy only; never interpret owner text as markup or links."""

import re

from django.core.exceptions import ValidationError
from django.utils.translation import get_language


def validate_public_text(value):
    if re.search(
        r"[<>]|(?:[a-z][a-z0-9+.-]*://|www\.|mailto:|tel:|javascript:|data:)|\[[^\]]*\]\(",
        value,
        re.I,
    ):
        raise ValidationError(
            "أدخل نصًا فقط دون وسوم أو روابط."
            if (get_language() or "ar").startswith("ar")
            else "Enter plain text without markup or links.",
            code="plain_text",
        )
