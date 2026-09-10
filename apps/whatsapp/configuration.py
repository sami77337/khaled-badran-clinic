"""Environment-backed configuration; diagnostics contain setting names only."""

import re
from urllib.parse import urlsplit

from django.conf import settings


TEMPLATE_KINDS = (
    "OTP",
    "CONSULTATION_REPLY",
    "BOOKING_CONFIRMATION",
    "APPOINTMENT_REMINDER",
    "LOCATION",
)


def website_origin():
    origin = settings.WHATSAPP_WEBSITE_ORIGIN
    if not isinstance(origin, str) or re.search(r"[\s\x00-\x1f\x7f\\]", origin):
        raise ValueError("WhatsApp website origin unavailable")
    origin = origin.rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.port == 0
    ):
        raise ValueError("WhatsApp website origin unavailable")
    return origin


def configuration_issues(*, templates=False):
    issues = []
    for name in (
        "ACCESS_TOKEN",
        "PHONE_NUMBER_ID",
        "WABA_ID",
        "APP_SECRET",
        "VERIFY_TOKEN",
        "GRAPH_VERSION",
    ):
        key = "WHATSAPP_META_" + name
        value = getattr(settings, key, "")
        if not isinstance(value, str) or not value.strip():
            issues.append(key)
    for name in ("PHONE_NUMBER_ID", "WABA_ID"):
        key = "WHATSAPP_META_" + name
        if not re.fullmatch(r"[0-9]{1,32}", str(getattr(settings, key, ""))):
            issues.append(key)
    if not re.fullmatch(
        r"v[0-9]{1,3}\.[0-9]{1,2}", settings.WHATSAPP_META_GRAPH_VERSION
    ):
        issues.append("WHATSAPP_META_GRAPH_VERSION")
    try:
        website_origin()
    except (ValueError, AttributeError):
        issues.append("WHATSAPP_WEBSITE_ORIGIN")
    if settings.WHATSAPP_DEFAULT_LANGUAGE not in {"ar", "en"}:
        issues.append("WHATSAPP_DEFAULT_LANGUAGE")
    if templates:
        for kind in TEMPLATE_KINDS:
            key = f"WHATSAPP_META_{kind}_TEMPLATE"
            if not re.fullmatch(r"[a-z0-9_]{1,512}", getattr(settings, key, "")):
                issues.append(key)
        for language in ("AR", "EN"):
            key = f"WHATSAPP_META_TEMPLATE_LANGUAGE_{language}"
            if not re.fullmatch(
                r"[a-z]{2,3}(?:_[A-Z]{2})?", getattr(settings, key, "")
            ):
                issues.append(key)
    return sorted(set(issues))


def is_available():
    return settings.WHATSAPP_META_ENABLED and not configuration_issues()
