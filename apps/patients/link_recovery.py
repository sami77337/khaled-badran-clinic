from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.booking.models import Appointment
from apps.patients.models import AppointmentLinkRecoveryChallenge, Patient
from apps.patients.otp import generate_otp_code, send_appointment_link_recovery_otp


OTP_LIFETIME_SECONDS = 10 * 60
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


class LinkRecoveryChallengeError(ValueError):
    pass


class LinkRecoveryConflictError(ValueError):
    pass


@dataclass(frozen=True)
class LinkRecoveryVerificationResult:
    succeeded: bool
    challenge: AppointmentLinkRecoveryChallenge | None = None
    reason: str = ""


@dataclass(frozen=True)
class LinkRecoveryCandidates:
    challenge: AppointmentLinkRecoveryChallenge
    appointments: tuple
    can_link: bool = False
    already_linked: bool = False
    conflict: bool = False


def _matching_appointments(phone_e164):
    return (
        Appointment.objects.filter(
            Q(contact_phone_e164=phone_e164)
            | Q(whatsapp_phone_e164=phone_e164)
            | Q(contact_phone_e164="", patient__phone_e164=phone_e164)
            | Q(whatsapp_phone_e164="", patient__whatsapp_phone_e164=phone_e164)
        )
        .select_related("patient", "visit_type")
        .order_by("starts_at", "id")
    )


def _create_and_send_challenge(*, user, phone_raw, phone_e164, language):
    now = timezone.now()
    code = generate_otp_code()
    AppointmentLinkRecoveryChallenge.objects.filter(
        user=user,
        consumed_at__isnull=True,
    ).update(consumed_at=now, updated_at=now)
    challenge = AppointmentLinkRecoveryChallenge.objects.create(
        user=user,
        phone_raw=phone_raw.strip(),
        phone_e164=phone_e164,
        otp_digest=make_password(code),
        expires_at=now
        + timedelta(
            seconds=getattr(
                settings,
                "APPOINTMENT_LINK_RECOVERY_OTP_TTL_SECONDS",
                OTP_LIFETIME_SECONDS,
            )
        ),
        max_attempts=OTP_MAX_ATTEMPTS,
        last_sent_at=now,
    )
    send_appointment_link_recovery_otp(phone_e164, code, language)
    return challenge


@transaction.atomic
def start_appointment_link_recovery(*, user, phone_raw, phone_e164, language):
    return _create_and_send_challenge(
        user=user,
        phone_raw=phone_raw,
        phone_e164=phone_e164,
        language=language,
    )


@transaction.atomic
def resend_appointment_link_recovery(*, user, challenge_id, language):
    challenge = AppointmentLinkRecoveryChallenge.objects.select_for_update().filter(
        public_id=challenge_id,
        user=user,
        consumed_at__isnull=True,
        verified_at__isnull=True,
    ).first()
    now = timezone.now()
    if (
        challenge is None
        or challenge.expires_at <= now
        or challenge.attempt_count >= challenge.max_attempts
    ):
        raise LinkRecoveryChallengeError("Verification request is unavailable.")
    cooldown = getattr(
        settings,
        "APPOINTMENT_LINK_RECOVERY_OTP_RESEND_COOLDOWN_SECONDS",
        OTP_RESEND_COOLDOWN_SECONDS,
    )
    if challenge.last_sent_at + timedelta(seconds=cooldown) > now:
        raise LinkRecoveryChallengeError("Verification code resend is cooling down.")
    return _create_and_send_challenge(
        user=user,
        phone_raw=challenge.phone_raw,
        phone_e164=challenge.phone_e164,
        language=language,
    )


@transaction.atomic
def verify_appointment_link_recovery(*, user, challenge_id, code):
    now = timezone.now()
    challenge = AppointmentLinkRecoveryChallenge.objects.select_for_update().filter(
        public_id=challenge_id,
        user=user,
    ).first()
    if (
        challenge is None
        or challenge.consumed_at is not None
        or challenge.verified_at is not None
    ):
        return LinkRecoveryVerificationResult(False, reason="unavailable")
    if challenge.expires_at <= now:
        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at", "updated_at"])
        return LinkRecoveryVerificationResult(False, reason="expired")
    if challenge.attempt_count >= challenge.max_attempts:
        return LinkRecoveryVerificationResult(False, reason="attempts")
    if not check_password(code, challenge.otp_digest):
        challenge.attempt_count += 1
        if challenge.attempt_count >= challenge.max_attempts:
            challenge.consumed_at = now
        challenge.save(update_fields=["attempt_count", "consumed_at", "updated_at"])
        return LinkRecoveryVerificationResult(
            False,
            reason="attempts" if challenge.consumed_at else "invalid",
        )

    challenge.verified_at = now
    challenge.otp_digest = make_password(None)
    challenge.save(update_fields=["verified_at", "otp_digest", "updated_at"])
    return LinkRecoveryVerificationResult(True, challenge=challenge)


def get_verified_recovery_candidates(*, user, challenge_id, for_update=False):
    challenge_query = AppointmentLinkRecoveryChallenge.objects
    if for_update:
        challenge_query = challenge_query.select_for_update()
    challenge = challenge_query.filter(
        public_id=challenge_id,
        user=user,
        consumed_at__isnull=True,
        verified_at__isnull=False,
        expires_at__gt=timezone.now(),
    ).first()
    if challenge is None:
        raise LinkRecoveryChallengeError("Verification request is unavailable.")

    appointments_query = _matching_appointments(challenge.phone_e164)
    if for_update:
        appointments_query = appointments_query.select_for_update(of=("self",))
    appointments = tuple(appointments_query)
    patient_ids = {appointment.patient_id for appointment in appointments}
    if len(patient_ids) != 1:
        return LinkRecoveryCandidates(
            challenge=challenge,
            appointments=(),
            conflict=len(patient_ids) > 1,
        )

    patient = appointments[0].patient
    if patient.user_id not in {None, user.id}:
        return LinkRecoveryCandidates(challenge=challenge, appointments=(), conflict=True)
    existing_profile = Patient.objects.filter(user=user).first()
    if existing_profile is not None and existing_profile.id != patient.id:
        return LinkRecoveryCandidates(challenge=challenge, appointments=(), conflict=True)
    return LinkRecoveryCandidates(
        challenge=challenge,
        appointments=appointments,
        can_link=patient.user_id is None,
        already_linked=patient.user_id == user.id,
    )


@transaction.atomic
def link_verified_recovery_patient(*, user, challenge_id):
    candidates = get_verified_recovery_candidates(
        user=user,
        challenge_id=challenge_id,
        for_update=True,
    )
    if candidates.conflict or not candidates.appointments:
        raise LinkRecoveryConflictError("Appointment recovery is unavailable.")

    patient_id = candidates.appointments[0].patient_id
    patient = Patient.objects.select_for_update().get(pk=patient_id)
    existing_profile = Patient.objects.select_for_update().filter(user=user).first()
    if patient.user_id not in {None, user.id}:
        raise LinkRecoveryConflictError("Appointment recovery is unavailable.")
    if existing_profile is not None and existing_profile.id != patient.id:
        raise LinkRecoveryConflictError("Appointment recovery is unavailable.")
    if patient.user_id is None:
        patient.user = user
        try:
            with transaction.atomic():
                patient.save(update_fields=["user", "updated_at"])
        except IntegrityError:
            raise LinkRecoveryConflictError("Appointment recovery is unavailable.") from None

    candidates.challenge.consumed_at = timezone.now()
    candidates.challenge.save(update_fields=["consumed_at", "updated_at"])
    return patient
