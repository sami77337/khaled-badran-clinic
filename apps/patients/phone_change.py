from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.booking.models import Appointment
from apps.booking.phone import normalize_phone
from apps.patients.models import AccountPhoneChangeChallenge, Patient
from apps.patients.otp import WhatsAppOtpServiceUnavailable, generate_otp_code, send_account_phone_change_otp
from apps.patients import temporary_otp
from apps.patients.profile_resolution import assert_profile_phone_available


OTP_LIFETIME_SECONDS = 10 * 60
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


class PhoneChangeConflictError(ValueError):
    pass


class PhoneChangeChallengeError(ValueError):
    pass


@dataclass(frozen=True)
class PhoneChangeVerificationResult:
    succeeded: bool
    user: object = None
    reason: str = ""


def _assert_phone_available(user, phone_e164):
    try:
        assert_profile_phone_available(phone_e164, user=user)
    except ValidationError:
        raise PhoneChangeConflictError("Phone cannot be used.") from None


def _assert_phone_changed(user, phone_e164):
    if user.username == phone_e164:
        raise PhoneChangeConflictError("Phone must differ from the current account phone.")


def _normalized_or_blank(value):
    try:
        return normalize_phone(value)
    except Exception:
        return ""


def _assert_verifiable_phone(user, phone_e164):
    """Validate ownership without creating or relinking any medical profile."""
    if not user.is_active or user.is_staff or user.is_superuser:
        raise PhoneChangeConflictError("Phone cannot be used.")
    patient = Patient.objects.select_for_update().filter(user=user).first()
    if temporary_otp.is_unverified(user):
        current_phone = _normalized_or_blank(user.username)
        if (
            patient is None or not current_phone
            or _normalized_or_blank(patient.phone) != current_phone
            or (patient.phone_raw and _normalized_or_blank(patient.phone_raw) != current_phone)
        ):
            raise PhoneChangeConflictError("Phone cannot be used.")
        _assert_phone_available(user, current_phone)
    else:
        _assert_phone_changed(user, phone_e164)
    _assert_phone_available(user, phone_e164)
    return patient


def _apply_patient_phone_change(*, patient, challenge, old_account_phone, now):
    future_appointments = list(
        Appointment.objects.select_for_update()
        .filter(
            patient=patient,
            starts_at__gt=now,
            status__in=[
                Appointment.Status.CONFIRMED,
                Appointment.Status.RESCHEDULED,
            ],
        )
        .order_by("id")
    )

    if challenge.propagate_to_upcoming_appointments:
        for appointment in future_appointments:
            update_fields = []
            if appointment.contact_phone_e164 == old_account_phone:
                appointment.contact_phone_raw = challenge.phone_raw
                appointment.contact_phone_e164 = challenge.phone_e164
                update_fields.extend(["contact_phone_raw", "contact_phone_e164"])
            if appointment.whatsapp_phone_e164 == old_account_phone:
                appointment.whatsapp_phone_raw = challenge.phone_raw
                appointment.whatsapp_phone_e164 = challenge.phone_e164
                update_fields.extend(["whatsapp_phone_raw", "whatsapp_phone_e164"])
            if update_fields:
                appointment.save(update_fields=[*update_fields, "updated_at"])
    else:
        # Legacy appointments with blank per-appointment fields currently inherit
        # from Patient. Freeze those effective values before changing Patient.
        for appointment in future_appointments:
            update_fields = []
            if not appointment.contact_phone_e164:
                effective_contact = appointment.effective_contact_phone
                normalized_contact = _normalized_or_blank(effective_contact)
                if normalized_contact:
                    appointment.contact_phone_raw = effective_contact
                    appointment.contact_phone_e164 = normalized_contact
                    update_fields.extend(["contact_phone_raw", "contact_phone_e164"])
            if not appointment.whatsapp_phone_e164:
                effective_whatsapp = appointment.effective_whatsapp_phone
                normalized_whatsapp = _normalized_or_blank(effective_whatsapp)
                if normalized_whatsapp:
                    appointment.whatsapp_phone_raw = effective_whatsapp
                    appointment.whatsapp_phone_e164 = normalized_whatsapp
                    update_fields.extend(["whatsapp_phone_raw", "whatsapp_phone_e164"])
            if update_fields:
                appointment.save(update_fields=[*update_fields, "updated_at"])

    patient.phone_raw = challenge.phone_raw
    patient.phone_e164 = challenge.phone_e164
    update_fields = ["phone_raw", "phone_e164", "updated_at"]
    if (
        challenge.propagate_to_upcoming_appointments
        and patient.whatsapp_phone_e164 == old_account_phone
    ):
        patient.whatsapp_phone_raw = challenge.phone_raw
        patient.whatsapp_phone_e164 = challenge.phone_e164
        update_fields.extend(["whatsapp_phone_raw", "whatsapp_phone_e164"])
    patient.save(update_fields=update_fields)


def _create_and_send_challenge(
    *,
    user,
    phone_raw,
    phone_e164,
    language,
    propagate_to_upcoming_appointments,
):
    now = timezone.now()
    code = generate_otp_code()
    AccountPhoneChangeChallenge.objects.filter(
        user=user,
        consumed_at__isnull=True,
    ).update(consumed_at=now, updated_at=now)
    challenge = AccountPhoneChangeChallenge.objects.create(
        user=user,
        phone_raw=phone_raw.strip(),
        phone_e164=phone_e164,
        propagate_to_upcoming_appointments=propagate_to_upcoming_appointments,
        otp_digest=make_password(code),
        expires_at=now + timedelta(
            seconds=getattr(settings, "ACCOUNT_PHONE_CHANGE_OTP_TTL_SECONDS", OTP_LIFETIME_SECONDS)
        ),
        max_attempts=OTP_MAX_ATTEMPTS,
        last_sent_at=now,
    )
    send_account_phone_change_otp(phone_e164, code, language)
    return challenge


@transaction.atomic
def start_account_phone_change(
    *,
    user,
    phone_raw,
    phone_e164,
    language,
    propagate_to_upcoming_appointments=True,
):
    if temporary_otp.enabled():
        raise WhatsAppOtpServiceUnavailable()
    locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
    if _normalized_or_blank(phone_raw) != phone_e164:
        raise PhoneChangeConflictError("Phone cannot be used.")
    _assert_phone_changed(locked_user, phone_e164)
    _assert_verifiable_phone(locked_user, phone_e164)
    return _create_and_send_challenge(
        user=locked_user,
        phone_raw=phone_raw,
        phone_e164=phone_e164,
        language=language,
        propagate_to_upcoming_appointments=propagate_to_upcoming_appointments,
    )


@transaction.atomic
def start_current_phone_verification(*, user, language):
    if temporary_otp.enabled():
        raise WhatsAppOtpServiceUnavailable()
    locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
    if not temporary_otp.is_unverified(locked_user):
        raise PhoneChangeConflictError("Verification request is unavailable.")
    phone = _normalized_or_blank(locked_user.username)
    _assert_verifiable_phone(locked_user, phone)
    return _create_and_send_challenge(
        user=locked_user,
        phone_raw=phone,
        phone_e164=phone,
        language=language,
        propagate_to_upcoming_appointments=False,
    )


@transaction.atomic
def resend_account_phone_change(*, user, challenge_id, language):
    if temporary_otp.enabled():
        raise WhatsAppOtpServiceUnavailable()
    locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
    challenge = AccountPhoneChangeChallenge.objects.select_for_update().filter(
        public_id=challenge_id,
        user=user,
        consumed_at__isnull=True,
    ).first()
    if challenge is None or challenge.expires_at <= timezone.now() or challenge.attempt_count >= challenge.max_attempts:
        raise PhoneChangeChallengeError("Verification request is unavailable.")
    cooldown = getattr(
        settings,
        "ACCOUNT_PHONE_CHANGE_OTP_RESEND_COOLDOWN_SECONDS",
        OTP_RESEND_COOLDOWN_SECONDS,
    )
    if challenge.last_sent_at + timedelta(seconds=cooldown) > timezone.now():
        raise PhoneChangeChallengeError("Verification code resend is cooling down.")
    _assert_verifiable_phone(locked_user, challenge.phone_e164)
    return _create_and_send_challenge(
        user=locked_user,
        phone_raw=challenge.phone_raw,
        phone_e164=challenge.phone_e164,
        language=language,
        propagate_to_upcoming_appointments=challenge.propagate_to_upcoming_appointments,
    )


@transaction.atomic
def verify_account_phone_change(*, user, challenge_id, code):
    if temporary_otp.enabled():
        return PhoneChangeVerificationResult(False, reason="unavailable")
    locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
    now = timezone.now()
    challenge = AccountPhoneChangeChallenge.objects.select_for_update().filter(
        public_id=challenge_id,
        user=user,
    ).first()
    if challenge is None or challenge.consumed_at is not None:
        return PhoneChangeVerificationResult(False, reason="unavailable")
    if challenge.expires_at <= now:
        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at", "updated_at"])
        return PhoneChangeVerificationResult(False, reason="expired")
    if challenge.attempt_count >= challenge.max_attempts:
        return PhoneChangeVerificationResult(False, reason="attempts")
    if not check_password(code, challenge.otp_digest):
        challenge.attempt_count += 1
        if challenge.attempt_count >= challenge.max_attempts:
            challenge.consumed_at = now
        challenge.save(update_fields=["attempt_count", "consumed_at", "updated_at"])
        return PhoneChangeVerificationResult(
            False,
            reason="attempts" if challenge.consumed_at else "invalid",
        )

    old_account_phone = _normalized_or_blank(locked_user.username) or locked_user.username
    try:
        patient = _assert_verifiable_phone(locked_user, challenge.phone_e164)
        with transaction.atomic():
            if old_account_phone != challenge.phone_e164:
                locked_user.username = challenge.phone_e164
                locked_user.save(update_fields=["username"])
                if patient is not None:
                    _apply_patient_phone_change(
                        patient=patient,
                        challenge=challenge,
                        old_account_phone=old_account_phone,
                        now=now,
                    )
            # Only this successful real-OTP path clears the persistent marker.
            locked_user.groups.remove(*locked_user.groups.filter(name=temporary_otp.UNVERIFIED_GROUP))
    except (PhoneChangeConflictError, IntegrityError):
        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at", "updated_at"])
        return PhoneChangeVerificationResult(False, reason="conflict")

    challenge.consumed_at = now
    challenge.save(update_fields=["consumed_at", "updated_at"])
    return PhoneChangeVerificationResult(True, user=locked_user)
