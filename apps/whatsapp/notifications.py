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
    safe delivery failures. Never log provider exceptions, phone or payload.
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


def send_reply_notification_if_consented(*, consultation_pk, guest=False):
    """Recheck recorded purpose consent after commit and on any retry."""
    try:
        from apps.patients.models import (
            CONSULTATION_WHATSAPP_REPLY_CONSENT_VERSION,
            Consultation, TransientConsultation,
        )

        model = TransientConsultation if guest else Consultation
        consultation = model.objects.filter(
            pk=consultation_pk,
            whatsapp_reply_consent_at__isnull=False,
            whatsapp_reply_consent_version=CONSULTATION_WHATSAPP_REPLY_CONSENT_VERSION,
            whatsapp_reply_consent_withdrawn_at__isnull=True,
        ).select_related(*([] if guest else ["patient__user"])).first()
        if consultation is None:
            return False
        # A later OTP verification cannot legitimize an alert to a guest
        # number that was not verified at the original submission.
        if guest and not consultation.phone_verified_at_submission:
            return False

        if guest:
            phone = consultation.phone_e164
        else:
            from apps.patients import temporary_otp

            owner = consultation.patient.user
            if (
                owner is None or not owner.is_active or owner.is_staff
                or temporary_otp.is_unverified(owner)
            ):
                return False
            phone = normalize_phone(owner.username)
            if consultation.patient.phone_e164 != phone:
                return False

        language = consultation.whatsapp_reply_consent_language
        language = "en" if language == "en" else "ar"
        route = "guest_consultation_detail" if guest else "patient_portal_consultation_detail"
        return send_reply_notification(
            phone_e164=phone,
            path=localized_url(route, language, public_id=consultation.public_id),
            language=language,
        )
    except Exception:
        # Database faults after commit must not surface clinical metadata or
        # turn a successfully saved reply into an apparent failed submission.
        logger.warning("Consultation reply alert consent check unavailable; saved reply retained.")
        return False

def schedule_reply_notification(consultation, *, guest=False):
    """Queue only a PK; no phone, clinical text or authorization snapshot."""
    transaction.on_commit(partial(
        send_reply_notification_if_consented, consultation_pk=consultation.pk, guest=guest,
    ))
