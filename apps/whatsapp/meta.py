"""Meta WhatsApp Cloud API adapter.

This module deliberately accepts only primitive notification/routing data. It
must never receive consultation bodies, medical media, clinical notes, or other
private medical content.
"""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from django.utils import timezone

from apps.booking.phone import normalize_phone


_GRAPH_VERSION_RE = re.compile(r"^v\d+\.\d+$")
_PHONE_NUMBER_ID_RE = re.compile(r"^\d+$")


class WhatsAppConfigurationError(ImproperlyConfigured):
    pass


class WhatsAppDeliveryError(RuntimeError):
    pass


def _setting(name: str, *, required: bool = True) -> str:
    value = str(getattr(settings, name, "") or "").strip()
    if required and not value:
        raise WhatsAppConfigurationError("WhatsApp provider configuration is unavailable.")
    return value


def provider_enabled() -> bool:
    return bool(getattr(settings, "WHATSAPP_META_ENABLED", False))


def _language(language: str) -> str:
    return "en" if language == "en" else "ar"


def _template_language(language: str) -> str:
    setting_name = (
        "WHATSAPP_META_TEMPLATE_LANGUAGE_EN"
        if _language(language) == "en"
        else "WHATSAPP_META_TEMPLATE_LANGUAGE_AR"
    )
    return _setting(setting_name)


def _recipient(phone_e164: str) -> str:
    normalized = normalize_phone(phone_e164)
    return normalized.lstrip("+")


def _graph_endpoint() -> str:
    if not provider_enabled():
        raise WhatsAppConfigurationError("WhatsApp provider configuration is unavailable.")
    version = _setting("WHATSAPP_META_GRAPH_VERSION")
    phone_number_id = _setting("WHATSAPP_META_PHONE_NUMBER_ID")
    if not _GRAPH_VERSION_RE.fullmatch(version) or not _PHONE_NUMBER_ID_RE.fullmatch(phone_number_id):
        raise WhatsAppConfigurationError("WhatsApp provider configuration is unavailable.")
    return f"https://graph.facebook.com/{version}/{phone_number_id}/messages"


def _post(payload: dict) -> bool:
    endpoint = _graph_endpoint()
    token = _setting("WHATSAPP_META_ACCESS_TOKEN")
    timeout = int(getattr(settings, "WHATSAPP_META_TIMEOUT_SECONDS", 10))
    request = Request(
        endpoint,
        data=json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if not 200 <= status < 300:
                raise WhatsAppDeliveryError("WhatsApp provider rejected the message.")
    except (HTTPError, URLError, OSError, ValueError):
        raise WhatsAppDeliveryError("WhatsApp provider delivery failed.") from None
    return True


def _base_payload(phone_e164: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _recipient(phone_e164),
    }


def send_text(phone_e164: str, text: str) -> bool:
    payload = _base_payload(phone_e164)
    payload.update({"type": "text", "text": {"preview_url": False, "body": text}})
    return _post(payload)


def send_template(phone_e164: str, template_name: str, language: str, components=None) -> bool:
    template = {
        "name": template_name,
        "language": {"code": _template_language(language)},
    }
    if components:
        template["components"] = components
    payload = _base_payload(phone_e164)
    payload.update({"type": "template", "template": template})
    return _post(payload)


def _website_origin() -> str:
    origin = _setting("WHATSAPP_WEBSITE_ORIGIN").rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise WhatsAppConfigurationError("WhatsApp website origin is unavailable.")
    return origin


def website_url(path: str) -> str:
    if not path.startswith("/") or path.startswith("//"):
        raise WhatsAppConfigurationError("WhatsApp website destination is invalid.")
    return _website_origin() + path


def _template_url_suffix(url: str) -> str:
    origin = _website_origin()
    if not url.startswith(origin + "/"):
        raise WhatsAppConfigurationError("WhatsApp website destination is invalid.")
    return url[len(origin) + 1 :]


def send_cta_url(phone_e164: str, *, body: str, label: str, url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise WhatsAppConfigurationError("WhatsApp CTA destination is invalid.")
    payload = _base_payload(phone_e164)
    payload.update(
        {
            "type": "interactive",
            "interactive": {
                "type": "cta_url",
                "body": {"text": body},
                "action": {
                    "name": "cta_url",
                    "parameters": {"display_text": label, "url": url},
                },
            },
        }
    )
    return _post(payload)


MAIN_MENU_COPY = {
    "ar": {
        "body": "أهلاً بك في عيادة الدكتور خالد بدران.\nكيف يمكننا مساعدتك؟",
        "button": "الخدمات",
        "section": "اختر الخدمة",
    },
    "en": {
        "body": "Welcome to Dr. Khaled Badran Clinic.\nHow can we help you?",
        "button": "Options",
        "section": "Choose a service",
    },
}

MAIN_MENU_ROWS = {
    "ar": (
        ("kbc_book", "حجز موعد"),
        ("kbc_consult", "استشارة طبية"),
        ("kbc_portal", "حساب المريض"),
        ("kbc_location", "موقع العيادة"),
        ("kbc_staff", "التحدث مع العيادة"),
    ),
    "en": (
        ("kbc_book", "Book Appointment"),
        ("kbc_consult", "Consultation"),
        ("kbc_portal", "Patient Account"),
        ("kbc_location", "Clinic Location"),
        ("kbc_staff", "Talk to the Clinic"),
    ),
}


def main_menu_payload(phone_e164: str, language: str = "ar") -> dict:
    language = _language(language)
    copy = MAIN_MENU_COPY[language]
    payload = _base_payload(phone_e164)
    payload.update(
        {
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": copy["body"]},
                "action": {
                    "button": copy["button"],
                    "sections": [
                        {
                            "title": copy["section"],
                            "rows": [
                                {"id": row_id, "title": title}
                                for row_id, title in MAIN_MENU_ROWS[language]
                            ],
                        }
                    ],
                },
            },
        }
    )
    return payload


def send_main_menu(phone_e164: str, language: str = "ar") -> bool:
    return _post(main_menu_payload(phone_e164, language))


def consultation_menu_payload(phone_e164: str, language: str = "ar") -> dict:
    language = _language(language)
    body = "اختر طريقة المتابعة:" if language == "ar" else "Choose how to continue:"
    choices = (
        (("kbc_consult_registered", "لدي حساب"), ("kbc_consult_guest", "المتابعة كزائر"))
        if language == "ar"
        else (("kbc_consult_registered", "I have an account"), ("kbc_consult_guest", "Continue as guest"))
    )
    payload = _base_payload(phone_e164)
    payload.update(
        {
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": row_id, "title": title},
                        }
                        for row_id, title in choices
                    ]
                },
            },
        }
    )
    return payload


def send_consultation_menu(phone_e164: str, language: str = "ar") -> bool:
    return _post(consultation_menu_payload(phone_e164, language))


def send_guest_otp(phone_e164: str, code: str, language: str) -> bool:
    """Existing guest OTP callable contract: (phone_e164, code, language)."""
    template_name = _setting("WHATSAPP_META_TEMPLATE_GUEST_OTP")
    components = [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": str(code)}],
        },
        {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": str(code)}],
        },
    ]
    return send_template(phone_e164, template_name, language, components)


def send_consultation_notice(phone_e164: str, message: str, website_url_value: str, language: str) -> bool:
    """Existing reply callable contract; the free-form message is not sent."""
    del message
    template_name = _setting("WHATSAPP_META_TEMPLATE_CONSULTATION_REPLY")
    suffix = _template_url_suffix(website_url_value)
    components = [
        {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": suffix}],
        }
    ]
    return send_template(phone_e164, template_name, language, components)


def _appointment_language(language: str | None = None) -> str:
    return _language(language or getattr(settings, "WHATSAPP_DEFAULT_LANGUAGE", "ar"))


def _appointment_time_text(appointment, language: str) -> str:
    local = timezone.localtime(appointment.starts_at)
    if language == "en":
        return local.strftime("%Y-%m-%d %H:%M")
    return local.strftime("%Y-%m-%d %H:%M")


def _appointment_detail_url(appointment, language: str) -> str:
    route = "patient_portal_appointment_detail_en" if language == "en" else "patient_portal_appointment_detail"
    path = reverse(route, kwargs={"public_token": appointment.public_token})
    return website_url(path)


def send_booking_confirmation(appointment, language: str | None = None) -> bool:
    language = _appointment_language(language)
    template_name = _setting("WHATSAPP_META_TEMPLATE_BOOKING_CONFIRMATION")
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": appointment.confirmation_reference},
                {"type": "text", "text": _appointment_time_text(appointment, language)},
            ],
        },
        {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [
                {"type": "text", "text": _template_url_suffix(_appointment_detail_url(appointment, language))}
            ],
        },
    ]
    return send_template(appointment.effective_whatsapp_phone, template_name, language, components)


def send_appointment_reminder(appointment, language: str | None = None) -> bool:
    language = _appointment_language(language)
    template_name = _setting("WHATSAPP_META_TEMPLATE_APPOINTMENT_REMINDER")
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": _appointment_time_text(appointment, language)},
                {"type": "text", "text": appointment.confirmation_reference},
            ],
        },
        {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [
                {"type": "text", "text": _template_url_suffix(_appointment_detail_url(appointment, language))}
            ],
        },
    ]
    return send_template(appointment.effective_whatsapp_phone, template_name, language, components)
