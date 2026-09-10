"""WhatsApp booking confirmation and reminder delivery."""

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.whatsapp.meta import _setting, _template_url_suffix, send_template, website_url


def _language(language=None):
    value = language or getattr(settings, "WHATSAPP_DEFAULT_LANGUAGE", "ar")
    return "en" if value == "en" else "ar"


def _appointment_time_text(appointment):
    return timezone.localtime(appointment.starts_at).strftime("%Y-%m-%d %H:%M")


def _public_appointment_url(appointment, language):
    route = "booking_success_en" if language == "en" else "booking_success"
    return website_url(reverse(route, kwargs={"public_token": appointment.public_token}))


def send_booking_confirmation(appointment, language=None):
    language = _language(language)
    template_name = _setting("WHATSAPP_META_TEMPLATE_BOOKING_CONFIRMATION")
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": appointment.confirmation_reference},
                {"type": "text", "text": _appointment_time_text(appointment)},
            ],
        },
        {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [
                {
                    "type": "text",
                    "text": _template_url_suffix(
                        _public_appointment_url(appointment, language)
                    ),
                }
            ],
        },
    ]
    return send_template(
        appointment.effective_whatsapp_phone,
        template_name,
        language,
        components,
    )


def send_appointment_reminder(appointment, language=None):
    language = _language(language)
    template_name = _setting("WHATSAPP_META_TEMPLATE_APPOINTMENT_REMINDER")
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": _appointment_time_text(appointment)},
                {"type": "text", "text": appointment.confirmation_reference},
            ],
        },
        {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [
                {
                    "type": "text",
                    "text": _template_url_suffix(
                        _public_appointment_url(appointment, language)
                    ),
                }
            ],
        },
    ]
    return send_template(
        appointment.effective_whatsapp_phone,
        template_name,
        language,
        components,
    )
