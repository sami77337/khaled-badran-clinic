"""Purpose-bound, versioned capabilities for anonymous patient rescheduling."""

from datetime import timezone as datetime_timezone
import json
from uuid import UUID

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.urls import reverse
from django.utils.crypto import salted_hmac

from apps.booking import operations, services
from apps.booking.models import Appointment


RESCHEDULE_SALT = "booking.patient-self-service-reschedule.v1"
RECEIPT_SALT = "booking.patient-self-service-reschedule-receipt.v1"
TOKEN_MAX_AGE = 30 * 24 * 60 * 60
RECEIPT_MAX_AGE = 60 * 60
SELF_SERVICE_NOTE = "Appointment rescheduled by patient through self-service link."
UNAVAILABLE = "Patient self-service rescheduling is unavailable."


def _version(appointment):
    # An old link must not revive if a later appointment is marked no-show again.
    values = [
        appointment.updated_at.astimezone(datetime_timezone.utc).isoformat(),
        appointment.starts_at.astimezone(datetime_timezone.utc).isoformat(),
        appointment.ends_at.astimezone(datetime_timezone.utc).isoformat(), appointment.doctor_id,
        appointment.visit_type_id, appointment.patient_id, appointment.status,
    ]
    return salted_hmac(RESCHEDULE_SALT, json.dumps(values)).hexdigest()


def _capability(appointment, salt):
    return signing.dumps(
        {"appointment": str(appointment.public_token), "version": _version(appointment)},
        salt=salt,
    )


def make_reschedule_token(appointment):
    """Issue from a persisted NO_SHOW appointment. No phone-based lookup or send."""
    if not appointment.pk or appointment.status != Appointment.Status.NO_SHOW:
        raise ValidationError(UNAVAILABLE)
    return _capability(appointment, RESCHEDULE_SALT)


def reschedule_url(appointment, *, language="ar"):
    """Relative secure URL for a future trusted delivery caller (no delivery here)."""
    return reverse(
        "patient_reschedule_en" if language == "en" else "patient_reschedule",
        kwargs={"token": make_reschedule_token(appointment)},
    )


def resolve_reschedule_token(token, *, for_update=False, receipt=False):
    salt = RECEIPT_SALT if receipt else RESCHEDULE_SALT
    max_age = RECEIPT_MAX_AGE if receipt else TOKEN_MAX_AGE
    try:
        payload = signing.loads(token, salt=salt, max_age=max_age)
        public_token = UUID(payload["appointment"])
        version = payload["version"]
    except (signing.BadSignature, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValidationError(UNAVAILABLE) from exc
    queryset = Appointment.objects.select_related("doctor", "visit_type")
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    appointment = queryset.filter(public_token=public_token).first()
    expected_status = Appointment.Status.RESCHEDULED if receipt else Appointment.Status.NO_SHOW
    if appointment is None or appointment.status != expected_status or _version(appointment) != version:
        raise ValidationError(UNAVAILABLE)
    return appointment


def patient_reschedule_appointment(*, token, starts_at):
    """Recheck the capability and shared availability rules inside the write locks."""
    try:
        with transaction.atomic():
            appointment = resolve_reschedule_token(token)
            services.lock_booking_doctor(appointment.doctor_id)
            appointment = resolve_reschedule_token(token, for_update=True)
            old_starts_at = appointment.starts_at
            starts_at, ends_at = operations.validate_reschedule_slot(appointment, starts_at)
            if starts_at == old_starts_at:
                raise ValidationError(UNAVAILABLE)
            appointment.starts_at = starts_at
            appointment.ends_at = ends_at
            appointment.status = Appointment.Status.RESCHEDULED
            appointment.reminder_sent_at = None
            appointment.full_clean()
            appointment.save(update_fields=[
                "starts_at", "ends_at", "status", "reminder_sent_at", "updated_at",
            ])
            operations._record_status_change(
                appointment,
                old_status=Appointment.Status.NO_SHOW,
                new_status=Appointment.Status.RESCHEDULED,
                old_starts_at=old_starts_at,
                new_starts_at=starts_at,
                note=SELF_SERVICE_NOTE,
                message=SELF_SERVICE_NOTE,
            )
            return appointment
    except (IntegrityError, OperationalError) as exc:
        # Includes an exact-slot constraint race and SQLite's competing write
        # failure. Catch outside atomic so appointment/history/audit roll back.
        raise ValidationError(UNAVAILABLE) from exc


def make_reschedule_receipt(appointment):
    """Read-only, short-lived success receipt; never accepted for rescheduling."""
    return _capability(appointment, RECEIPT_SALT)
