import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.patients.models import AccountPhoneChangeChallenge, Patient
from apps.patients.otp import send_account_phone_change_otp


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


def _generate_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def _assert_phone_available(user, phone_e164):
    user_model = get_user_model()
    if user_model.objects.filter(username=phone_e164).exclude(pk=user.pk).exists():
        raise PhoneChangeConflictError("Phone cannot be used.")
    if Patient.objects.filter(phone_e164=phone_e164).exclude(user=user).exists():
        raise PhoneChangeConflictError("Phone cannot be used.")


def _assert_phone_changed(user, phone_e164):
    if user.username == phone_e164:
        raise PhoneChangeConflictError("Phone must differ from the current account phone.")


def _create_and_send_challenge(*, user, phone_raw, phone_e164, language):
    now = timezone.now()
    code = _generate_code()
    AccountPhoneChangeChallenge.objects.filter(
        user=user,
        consumed_at__isnull=True,
    ).update(consumed_at=now, updated_at=now)
    challenge = AccountPhoneChangeChallenge.objects.create(
        user=user,
        phone_raw=phone_raw.strip(),
        phone_e164=phone_e164,
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
def start_account_phone_change(*, user, phone_raw, phone_e164, language):
    locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
    _assert_phone_changed(locked_user, phone_e164)
    _assert_phone_available(locked_user, phone_e164)
    return _create_and_send_challenge(
        user=locked_user,
        phone_raw=phone_raw,
        phone_e164=phone_e164,
        language=language,
    )


@transaction.atomic
def resend_account_phone_change(*, user, challenge_id, language):
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
    locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
    _assert_phone_changed(locked_user, challenge.phone_e164)
    _assert_phone_available(locked_user, challenge.phone_e164)
    return _create_and_send_challenge(
        user=locked_user,
        phone_raw=challenge.phone_raw,
        phone_e164=challenge.phone_e164,
        language=language,
    )


@transaction.atomic
def verify_account_phone_change(*, user, challenge_id, code):
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

    locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
    try:
        _assert_phone_changed(locked_user, challenge.phone_e164)
        _assert_phone_available(locked_user, challenge.phone_e164)
        with transaction.atomic():
            locked_user.username = challenge.phone_e164
            locked_user.save(update_fields=["username"])
    except (PhoneChangeConflictError, IntegrityError):
        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at", "updated_at"])
        return PhoneChangeVerificationResult(False, reason="conflict")

    patient = Patient.objects.select_for_update().filter(user=locked_user).first()
    if patient is not None:
        patient.phone_raw = challenge.phone_raw
        patient.phone_e164 = challenge.phone_e164
        patient.save(update_fields=["phone_raw", "phone_e164", "updated_at"])

    challenge.consumed_at = now
    challenge.save(update_fields=["consumed_at", "updated_at"])
    return PhoneChangeVerificationResult(True, user=locked_user)
