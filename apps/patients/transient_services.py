"""Guest phone verification and consultation-specific access grants."""

import logging
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.booking.phone import normalize_phone
from apps.booking.rate_limits import get_client_ip
from apps.patients.models import (
    CONSULTATION_MAX_ATTACHMENTS, TransientConsultation,
    TransientConsultationAttachment, TransientConsultationChallenge,
    validate_consultation_upload,
)
from apps.patients.otp import generate_otp_code, _send_whatsapp_otp, WhatsAppOtpServiceUnavailable
from apps.patients.rate_limits import _rate_limit, _setting_int
from apps.notifications.services import schedule_staff_event

logger = logging.getLogger(__name__)
SESSION_KEY = "guest_consultation_browser_secret"


class GuestAccessDenied(ValueError):
    pass


def session_digest(request, *, create=False):
    secret = request.session.get(SESSION_KEY)
    if not secret and create:
        secret = secrets.token_urlsafe(32)
        request.session[SESSION_KEY] = secret
    if not secret:
        return ""
    return salted_hmac("guest-consultation-session", secret, algorithm="sha256").hexdigest()


def masked_phone(phone):
    return "••••••" + phone[-3:]


def check_limit(request, action, phone=""):
    """Independent IP and normalized-phone limits; cache failure fails closed."""
    defaults = {"send": (10, 5), "verify": (30, 20), "submit": (10, 5)}
    try:
        results = []
        for kind, identity, default in (
            ("IP", get_client_ip(request), defaults[action][0]),
            ("PHONE", phone, defaults[action][1]),
        ):
            if identity:
                results.append(_rate_limit(
                    f"guest-{action}-{kind.lower()}", identity,
                    limit=_setting_int(f"GUEST_CONSULTATION_{action.upper()}_{kind}_PER_HOUR", default),
                    timeout=3600, message="Guest consultation rate limit reached.",
                ).allowed)
        if action == "send" and phone:
            results.append(_rate_limit(
                "guest-send-cooldown", phone, limit=1,
                timeout=_setting_int("GUEST_CONSULTATION_SEND_COOLDOWN_SECONDS", 60),
                message="Guest consultation rate limit reached.",
            ).allowed)
        return all(results)
    except Exception:
        logger.warning("Guest consultation rate limiter unavailable; request denied.")
        return False


def challenges(request, consultation=None):
    return TransientConsultationChallenge.objects.filter(
        session_digest=session_digest(request), consultation=consultation, revoked_at__isnull=True,
    ).exclude(session_digest="")


def active_grant(request, consultation=None):
    return challenges(request, consultation).filter(
        verified_at__isnull=False, grant_expires_at__gt=timezone.now(),
    ).order_by("-created_at").first()


def pending_challenge(request, consultation=None):
    return challenges(request, consultation).filter(verified_at__isnull=True).order_by("-created_at").first()


def start_challenge(request, *, phone, language, consultation=None):
    # A deep-link verification destination always comes from the database.
    phone = consultation.phone_e164 if consultation else normalize_phone(phone)
    if not check_limit(request, "send", phone):
        return None
    digest = session_digest(request, create=True)
    code = generate_otp_code()
    now = timezone.now()
    with transaction.atomic():
        challenges(request, consultation).filter(verified_at__isnull=True).update(revoked_at=now)
        challenge = TransientConsultationChallenge.objects.create(
            consultation=consultation, session_digest=digest, phone_e164=phone,
            otp_digest=make_password(code),
            expires_at=now + timedelta(seconds=_setting_int("GUEST_CONSULTATION_OTP_TTL_SECONDS", 600)),
        )
    try:
        _send_whatsapp_otp(setting_name="GUEST_CONSULTATION_OTP_SENDER",
                           phone_e164=phone, code=code, language=language)
    except Exception:
        TransientConsultationChallenge.objects.filter(pk=challenge.pk).update(revoked_at=timezone.now())
        logger.warning("Guest consultation verification delivery unavailable.")
        raise WhatsAppOtpServiceUnavailable("Verification delivery unavailable.") from None
    return challenge


def verify_challenge(request, *, challenge, code):
    if not check_limit(request, "verify", challenge.phone_e164):
        return "limited"
    with transaction.atomic():
        locked = TransientConsultationChallenge.objects.select_for_update().get(pk=challenge.pk)
        now = timezone.now()
        if (locked.session_digest != session_digest(request) or locked.revoked_at
                or locked.verified_at or locked.attempt_count >= _setting_int("GUEST_CONSULTATION_OTP_MAX_ATTEMPTS", 5)):
            return "invalid"
        if locked.expires_at <= now:
            return "expired"
        locked.attempt_count += 1
        valid = check_password(code, locked.otp_digest)
        if valid:
            locked.verified_at = now
            locked.grant_expires_at = now + timedelta(
                seconds=_setting_int("GUEST_CONSULTATION_GRANT_TTL_SECONDS", 86400),
            )
            locked.otp_digest = ""
        locked.save(update_fields=["attempt_count", "verified_at", "grant_expires_at", "otp_digest"])
    if valid:
        request.session.cycle_key()
    return "verified" if valid else "invalid"


def create_guest_consultation(request, *, question, display_name, uploaded_files, language):
    files = list(uploaded_files or [])
    if len(files) > CONSULTATION_MAX_ATTACHMENTS:
        raise ValidationError("Too many attachments.")
    metadata = [validate_consultation_upload(item) for item in files]
    stored = []
    try:
        with transaction.atomic():
            grant = challenges(request).select_for_update().filter(
                verified_at__isnull=False, grant_expires_at__gt=timezone.now(),
            ).order_by("-created_at").first()
            if grant is None:
                raise GuestAccessDenied("Verified entry grant required.")
            consultation = TransientConsultation(
                phone_e164=grant.phone_e164, display_name=display_name.strip(),
                question=question.strip(), language=language,
            )
            consultation.full_clean()
            consultation.save()
            for upload, info in zip(files, metadata):
                attachment = TransientConsultationAttachment(consultation=consultation, file=upload, **info)
                try:
                    attachment.save()
                finally:
                    if attachment.file and getattr(attachment.file, "_committed", False):
                        stored.append((attachment.file.storage, attachment.file.name))
            grant.consultation = consultation
            grant.save(update_fields=["consultation"])
            schedule_staff_event("new-consultation")
        return consultation
    except Exception:
        for storage, name in stored:
            try:
                storage.delete(name)
            except Exception:
                logger.warning("Guest consultation failed-upload cleanup unavailable.")
        raise
