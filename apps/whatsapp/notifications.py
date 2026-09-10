"""Neutral reply notifications. Only primitive, non-medical data reaches senders."""

import logging
from functools import partial
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string

from apps.booking.phone import normalize_phone
from apps.whatsapp.actions import localized_url

logger = logging.getLogger(__name__)

REPLY_MESSAGES = {
    "ar": "تم إضافة رد جديد من عيادة الدكتور خالد بدران على استشارتك.",
    "en": "Dr. Khaled Badran Clinic has added a new reply to your consultation.",
}


def send_reply_notification(*, phone_e164, path, language):
    """Callable signature: (phone_e164, message, website_url, language).

    Runs after commit; missing configuration, False results and exceptions are
    delivery failures. Never log provider exceptions, phone or payload.
    """
    try:
        sender = settings.WHATSAPP_CONSULTATION_NOTIFICATION_SENDER
        origin = settings.WHATSAPP_WEBSITE_ORIGIN.rstrip("/")
        parsed = urlsplit(origin)
        if (not sender or parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment):
            raise ValueError("Notification configuration unavailable")
        if isinstance(sender, str):
            sender = import_string(sender)
        if not callable(sender) or not path.startswith("/") or path.startswith("//"):
            raise ValueError("Notification configuration unavailable")
        result = sender(normalize_phone(phone_e164), REPLY_MESSAGES[language], origin + path, language)
        if result is False:
            raise ValueError("Notification delivery unavailable")
        return True
    except Exception:
        logger.warning("Consultation reply notification delivery unavailable; saved reply retained.")
        return False


def schedule_reply_notification(consultation, *, guest=False):
    language = consultation.language if guest else getattr(settings, "WHATSAPP_DEFAULT_LANGUAGE", "ar")
    language = "en" if language == "en" else "ar"
    phone = consultation.phone_e164 if guest else (
        consultation.patient.whatsapp_phone_e164 or consultation.patient.phone_e164
    )
    route = "guest_consultation_detail" if guest else "patient_portal_consultation_detail"
    transaction.on_commit(partial(
        send_reply_notification, phone_e164=phone,
        path=localized_url(route, language, public_id=consultation.public_id), language=language,
    ))
